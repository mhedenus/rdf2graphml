import urllib.request
import urllib.error
import http.cookiejar
import base64
import logging
import io
import time
import hashlib
import json
from pathlib import Path
from PIL import Image
import tempfile

logger = logging.getLogger(__name__)

# --- Cache Konfiguration ---
CACHE_DIR = Path(tempfile.gettempdir()) / "rdf2graphml_cache"



def _init_cache():
    """Erstellt das Cache-Verzeichnis, falls es nicht existiert."""
    if not CACHE_DIR.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_cache_key(source, target_height):
    """Generiert einen eindeutigen MD5-Hash für die URL/Pfad-Höhen-Kombination."""
    unique_string = f"{source}_{target_height}"
    return hashlib.md5(unique_string.encode('utf-8')).hexdigest()


# --- Globale Cookie-Verwaltung einrichten ---
# Wir bauen einen "Opener", der bei jedem Aufruf automatisch Cookies sammelt und mitsendet.
# Dies ist entscheidend, um sessionbasiertes Rate-Limiting (Bot-Schutz) zu umgehen.
cookie_jar = http.cookiejar.CookieJar()
cookie_processor = urllib.request.HTTPCookieProcessor(cookie_jar)
opener = urllib.request.build_opener(cookie_processor)


def _download_with_backoff(url, max_wait=20):
    """
    Lädt eine URL herunter und behandelt HTTP 429, 403, 503 mit Exponential Backoff.
    Nutzt Cookies und Browser-Header zur Vermeidung von Bot-Blockaden.
    """
    total_waited = 0
    current_delay = 2.0  # Startwert für das Exponential Backoff in Sekunden

    # Erweiterte Header, um WAFs (Cloudflare etc.) nicht zu triggern
    browser_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
    }

    # BREMSE: Wir warten pauschal 1 Sekunde vor JEDEM neuen Download,
    # damit wir das Rate-Limit des Servers gar nicht erst auslösen.
    time.sleep(1)

    while True:
        try:
            req = urllib.request.Request(url, headers=browser_headers)

            # Wir nutzen den Opener mit dem integrierten CookieJar statt urlopen
            with opener.open(req, timeout=10) as response:
                return response.read()

        except urllib.error.HTTPError as e:
            if e.code in (429, 403, 503):
                if total_waited + current_delay > max_wait:
                    logger.error(f"Timeout: Maximale Zeit ({max_wait}s) für {url} überschritten (HTTP {e.code}).")
                    return None

                logger.warning(f"HTTP {e.code}. Server blockt ab. Warte {current_delay}s vor Retry für {url}...")
                time.sleep(current_delay)
                total_waited += current_delay
                current_delay *= 2  # Verdopple die Wartezeit beim nächsten Versuch
            else:
                logger.error(f"HTTP Fehler {e.code} beim Laden von {url}")
                return None

        except Exception as e:
            logger.warning(f"Verbindungsfehler beim Laden von {url}: {e}")
            return None


def _scale_and_encode(image_bytes, target_height):
    """Skaliert ein Bild proportional auf target_height und gibt (Base64-PNG, target_width) zurück."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            aspect_ratio = img.width / img.height
            target_width = int(target_height * aspect_ratio)

            # LANCZOS liefert die beste Qualität beim Verkleinern von Bildern
            img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img_resized.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode('utf-8'), target_width
    except Exception as e:
        logger.error(f"Bildverarbeitungsfehler: {e}")
        return None, None


def load_image_as_base64(source, is_local=False, target_height=64, base_dir=None):
    """
    Hauptfunktion: Lädt Bild (mit Cache, Backoff und Cookies), skaliert es und encodiert es.
    Wenn is_local=True, wird source relativ zu base_dir aufgelöst.
    """
    _init_cache()

    # 1. Im Cache nachsehen
    cache_key = _get_cache_key(source, target_height)
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f" -> Lade Bild aus Cache: {source} -> {cache_file}")
                return data["base64"], data["width"]
        except Exception as e:
            logger.warning(f"Cache-Datei beschädigt ({e}), lade neu...")

    # 2. Bild laden (Lokal oder via Download)
    if is_local:
        path = Path(source)

        # Den base_dir vor den Pfad hängen, falls es ein relativer Pfad ist
        if base_dir and not path.is_absolute():
            path = Path(base_dir) / path

        if not path.exists():
            logger.warning(f"Lokale Bild-Datei nicht gefunden: {path}")
            return None, None
        try:
            image_data = path.read_bytes()
        except Exception as e:
            logger.error(f"Fehler beim Lesen der lokalen Datei {path}: {e}")
            return None, None
    else:
        image_data = _download_with_backoff(source, max_wait=20)
        if not image_data:
            return None, None

    # 3. Bild verarbeiten
    b64_str, width = _scale_and_encode(image_data, target_height)

    # 4. In den Cache schreiben, falls die Verarbeitung erfolgreich war
    if b64_str and width:
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({"base64": b64_str, "width": width}, f)
        except Exception as e:
            logger.warning(f"Konnte Bild nicht in Cache schreiben: {e}")

    return b64_str, width