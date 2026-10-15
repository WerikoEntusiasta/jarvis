from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import hardware_control as hc

router = APIRouter(prefix="/api/hardware", tags=["Hardware & Systems Telemetry"])

@router.get("/telemetry")
async def get_telemetry():
    """Retorna telemetria em tempo real de CPU, RAM, GPU NVIDIA GTX 1660 Ti e SSDs."""
    try:
        data = hc.get_hardware_telemetry()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter telemetria: {e}")

@router.get("/savings")
async def get_savings():
    """Retorna métricas de economia de tokens e processamento offline local."""
    try:
        data = hc.get_local_savings_telemetry()
        return JSONResponse(content=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter métricas de economia: {e}")

@router.post("/volume")
async def set_system_volume(request: Request):
    """Ajusta ou consulta o volume do sistema Windows."""
    try:
        body = await request.json()
        level = body.get("level")
        if level is not None:
            res = hc.set_master_volume(level)
            return JSONResponse(content={"status": "success", "level": level, "details": res})
        cur_vol = hc.get_master_volume()
        return JSONResponse(content={"status": "success", "current_volume": cur_vol})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ajustar volume: {e}")
