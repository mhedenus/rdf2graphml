import base64
import hashlib
import http.cookiejar
import io
import json
import logging
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# --- Cache Configuration ---
CACHE_DIR = Path(tempfile.gettempdir()) / "rdf2graphml_cache"


def _init_cache():
    """Creates the cache directory if it doesn't exist."""
    if not CACHE_DIR.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_cache_key(source, target_height):
    """Generates a unique MD5 hash for the URL/path-height combination."""
    unique_string = f"{source}_{target_height}"
    return hashlib.md5(unique_string.encode('utf-8')).hexdigest()


# --- Set up global cookie management ---
# We build an "opener" that automatically collects and sends cookies with every request.
# This is crucial to bypass session-based rate limiting (bot protection).
cookie_jar = http.cookiejar.CookieJar()
cookie_processor = urllib.request.HTTPCookieProcessor(cookie_jar)
opener = urllib.request.build_opener(cookie_processor)


def _download_with_backoff(url, max_wait=20):
    """
    Downloads a URL and handles HTTP 429, 403, 503 with exponential backoff.
    Uses cookies and browser headers to avoid bot blocking.
    """
    total_waited = 0
    current_delay = 2.0  # Initial value for exponential backoff in seconds

    # Extended headers to avoid triggering WAFs (Cloudflare etc.)
    browser_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    # BRAKE: We wait a flat 1 second before EVERY new download
    # so that we don't trigger the server's rate limit in the first place.
    time.sleep(1)

    while True:
        try:
            req = urllib.request.Request(url, headers=browser_headers)

            # We use the opener with the integrated CookieJar instead of urlopen
            with opener.open(req, timeout=10) as response:
                return response.read()

        except urllib.error.HTTPError as e:
            if e.code in (429, 403, 503):
                if total_waited + current_delay > max_wait:
                    logger.error(f"Timeout: Maximum time ({max_wait}s) for {url} exceeded (HTTP {e.code}).")
                    return None

                logger.warning(f"HTTP {e.code}. Server is blocking. Waiting {current_delay}s before retrying {url}...")
                time.sleep(current_delay)
                total_waited += current_delay
                current_delay *= 2  # Double the wait time on the next attempt
            else:
                logger.error(f"HTTP error {e.code} while loading {url}")
                return None

        except Exception as e:
            logger.warning(f"Connection error while loading {url}: {e}")
            return None


def _scale_and_encode(image_bytes, target_height):
    """Scales an image proportionally to target_height and returns (Base64-PNG, target_width)."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            aspect_ratio = img.width / img.height
            target_width = int(target_height * aspect_ratio)

            # LANCZOS provides the best quality when downscaling images
            img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img_resized.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode('utf-8'), target_width
    except Exception as e:
        logger.error(f"Image processing error: {e}")
        return None, None


def load_icon_as_base64(source, is_local=False, target_height=64, base_dir=None):
    """
    Main function: Loads an image (with cache, backoff, and cookies), scales it, and encodes it.
    If is_local=True, source is resolved relative to base_dir.
    """
    _init_cache()

    # 1. Check the cache
    cache_key = _get_cache_key(source, target_height)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f" -> Loading image from cache: {source} -> {cache_file}")
                return data["base64"], data["width"]
        except Exception as e:
            logger.warning(f"Cache file corrupted ({e}), reloading...")

    # 2. Load image (local or via download)
    if is_local:
        path = Path(source)

        # Prepend base_dir to the path if it is a relative path
        if base_dir and not path.is_absolute():
            path = Path(base_dir) / path

        if not path.exists():
            logger.warning(f"Local image file not found: {path}")
            return None, None
        try:
            image_data = path.read_bytes()
        except Exception as e:
            logger.error(f"Error reading local file {path}: {e}")
            return None, None
    else:
        image_data = _download_with_backoff(source, max_wait=20)
        if not image_data:
            return None, None

    # 3. Process image
    b64_str, width = _scale_and_encode(image_data, target_height)

    # 4. Write to cache if processing was successful
    if b64_str and width:
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({"base64": b64_str, "width": width}, f)
        except Exception as e:
            logger.warning(f"Could not write image to cache: {e}")

    return b64_str, width
