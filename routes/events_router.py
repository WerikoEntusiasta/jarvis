import asyncio
import json
import queue
import threading
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="", tags=["SSE Realtime Events"])

sse_subscribers = []
sse_lock = threading.Lock()

def broadcast_hud_event(event_type: str, data: dict):
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with sse_lock:
        to_remove = []
        for q in sse_subscribers:
            try:
                q.put_nowait(msg)
            except Exception:
                to_remove.append(q)
        for q in to_remove:
            if q in sse_subscribers:
                sse_subscribers.remove(q)

@router.get("/events")
@router.get("/api/events")
async def sse_endpoint():
    q = queue.Queue(maxsize=50)
    with sse_lock:
        sse_subscribers.append(q)

    async def event_generator():
        try:
            yield "event: connected\ndata: {\"status\": \"ONLINE\", \"system\": \"JARVIS HUD SSE\"}\n\n"
            while True:
                while not q.empty():
                    msg = q.get_nowait()
                    yield msg
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            with sse_lock:
                if q in sse_subscribers:
                    sse_subscribers.remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
