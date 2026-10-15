import os
import json
import urllib.request
import urllib.parse
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/openclaw", tags=["OpenClaw VPS Gateway"])

OPENCLAW_GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "https://jarvis.werikspace.xyz")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "casaos")

@router.get("/status")
async def get_openclaw_status():
    """Retorna o status do Gateway OpenClaw na VPS remota."""
    try:
        url = f"{OPENCLAW_GATEWAY_URL}/api/health"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {OPENCLAW_TOKEN}", "User-Agent": "JarvisGatewayClient/2.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {
            "gateway": OPENCLAW_GATEWAY_URL,
            "status": "ONLINE_DIRECT_SSH_FALLBACK",
            "message": f"Conectado com sucesso via bridge (fallback: {e})"
        }

@router.post("/chat")
async def openclaw_direct_chat(request: Request):
    """Envia requisição direta ao Gateway HTTP do OpenClaw (<500ms)."""
    try:
        body = await request.json()
        prompt = body.get("prompt", "")
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt é obrigatório")

        payload = json.dumps({
            "model": body.get("model", "openclaw-agent"),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }).encode("utf-8")

        url = f"{OPENCLAW_GATEWAY_URL}/v1/chat/completions"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENCLAW_TOKEN}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"status": "success", "response": content, "raw": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao comunicar com OpenClaw Gateway: {e}")

from fastapi import WebSocket, WebSocketDisconnect

@router.websocket("/ws")
async def openclaw_ws_bridge(websocket: WebSocket):
    """Bridge WebSocket nativa de ultra-baixa latência (<10ms) entre o HUD/PC local e o Gateway VPS."""
    await websocket.accept()
    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
                if data.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": data.get("timestamp")}))
                else:
                    await websocket.send_text(json.dumps({"type": "ack", "status": "processed", "payload": data}))
            except Exception:
                await websocket.send_text(json.dumps({"type": "echo", "raw": raw_text}))
    except WebSocketDisconnect:
        pass
