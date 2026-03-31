import os
import requests
from flask import Flask, Response, abort

app = Flask(__name__)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("Umgebungsvariable GITHUB_TOKEN fehlt!")

# Basis-URL deines Repos
BASE_URL = "https://raw.githubusercontent.com/mhedenus/o-o/main/"

@app.route("/<path:filepath>")
def proxy_file(filepath):
    url = BASE_URL + filepath

    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    r = requests.get(url, headers=headers, stream=True)

    if r.status_code != 200:
        abort(r.status_code)

    return Response(
        r.iter_content(chunk_size=8192),
        content_type=r.headers.get("Content-Type", "application/octet-stream")
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)