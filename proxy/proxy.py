"""Single-origin reverse proxy for VideoPocket.

Serves the static frontend at "/" and forwards everything under "/api/" to
the local backend, so the whole app (UI + API + file download) is reachable
through one origin — which is what gets exposed via the Cloudflare Tunnel.

Streams request/response bodies rather than buffering them, so large MP4
downloads do not sit fully in this process's memory.
"""
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://127.0.0.1:8200")
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8080"))

# No per-request timeout cap for downloads: long videos can legitimately take
# a while to stream through. Connect/read limits still apply individually.
_client = httpx.AsyncClient(base_url=BACKEND_BASE_URL, timeout=httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0))

app = FastAPI(title="VideoPocket Proxy")

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "OPTIONS"])
async def proxy_api(path: str, request: Request):
    url = f"/api/{path}"
    body = await request.body()

    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")
    }

    upstream_request = _client.build_request(
        request.method,
        url,
        params=request.query_params,
        headers=forward_headers,
        content=body,
    )
    upstream_response = await _client.send(upstream_request, stream=True)

    response_headers = {
        k: v for k, v in upstream_response.headers.items() if k.lower() not in HOP_BY_HOP_HEADERS
    }

    async def body_stream():
        async for chunk in upstream_response.aiter_bytes():
            yield chunk
        await upstream_response.aclose()

    return StreamingResponse(
        body_stream(),
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "proxy": "ok"}


# Static frontend last, so it does not shadow /api/* or /health above.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
