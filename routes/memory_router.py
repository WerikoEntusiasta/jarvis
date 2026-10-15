import os
import json
import urllib.request
import urllib.parse
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(prefix="", tags=["Memory & Brain"])

MEMORY_PRIMARY_URL = os.environ.get("MEMORY_PRIMARY_URL", "${ZIMA_ROUTER_URL:-http://127.0.0.1:8095}")
MEMORY_FALLBACK_URL = os.environ.get("MEMORY_FALLBACK_URL", "http://127.0.0.1:8090")
DIRECTORY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _forward_to_memory_service(method: str, path: str, body: bytes = None, headers: dict = None):
    req_headers = {"User-Agent": "JarvisProxy/1.0"}
    if headers and "content-type" in headers:
        req_headers["Content-Type"] = headers["content-type"]
        
    for base_url in [MEMORY_PRIMARY_URL, MEMORY_FALLBACK_URL]:
        try:
            url = f"{base_url}{path}"
            req = urllib.request.Request(url, data=body if body else None, headers=req_headers, method=method)
            with urllib.request.urlopen(req, timeout=4) as resp:
                return resp.status, resp.read()
        except Exception:
            continue
    raise HTTPException(status_code=503, detail="Nenhum serviço de memória disponível (ZimaOS ou Local)")

@router.get("/memory", response_class=HTMLResponse)
@router.get("/memory/", response_class=HTMLResponse)
@router.get("/brain", response_class=HTMLResponse)
@router.get("/brain/", response_class=HTMLResponse)
async def serve_memory_dashboard():
    dash_path = os.path.join(DIRECTORY, "memory", "brain_dashboard.html")
    if os.path.exists(dash_path):
        with open(dash_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    return HTMLResponse("<h1>J.A.R.V.I.S. Memory Dashboard Not Found</h1>", status_code=404)

@router.get("/api/memory/{path:path}")
async def proxy_memory_get(path: str, request: Request):
    full_path = f"/api/memory/{path}"
    if request.query_params:
        full_path += f"?{request.query_params}"
    status_code, content = _forward_to_memory_service("GET", full_path)
    return Response(content=content, status_code=status_code, media_type="application/json")

@router.post("/api/memory/{path:path}")
async def proxy_memory_post(path: str, request: Request):
    full_path = f"/api/memory/{path}"
    body = await request.body()
    headers = dict(request.headers)
    status_code, content = _forward_to_memory_service("POST", full_path, body=body, headers=headers)
    return Response(content=content, status_code=status_code, media_type="application/json")

@router.delete("/api/memory/{path:path}")
async def proxy_memory_delete(path: str, request: Request):
    full_path = f"/api/memory/{path}"
    status_code, content = _forward_to_memory_service("DELETE", full_path)
    return Response(content=content, status_code=status_code, media_type="application/json")
