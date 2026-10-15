from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse
import biometrics

router = APIRouter(prefix="/api", tags=["Biometrics & Authentication"])

@router.get("/auth/status")
async def auth_status():
    """Retorna status da autenticação biométrica facial e sessão atual."""
    return JSONResponse(content={
        "enabled": biometrics.is_portal_enabled(),
        "profiles_count": len(biometrics.load_face_profiles())
    })

@router.post("/enroll/register")
async def register_face_profile(request: Request):
    """Cadastra um novo perfil de reconhecimento facial."""
    body = await request.json()
    name = body.get("name", "Operador")
    role = body.get("role", "Operador Autorizado")
    descriptor = body.get("descriptor")
    if not descriptor:
        raise HTTPException(status_code=400, detail="Descriptor facial é obrigatório")
    res = biometrics.register_face_profile(name, role, descriptor)
    return JSONResponse(content=res)

@router.post("/enroll/delete")
async def delete_face_profile(request: Request, x_enroll_key: str = Header(None, alias="X-Enroll-Key")):
    """Remove um perfil facial cadastrado."""
    if not biometrics.verify_enrollment_password(x_enroll_key or ""):
        raise HTTPException(status_code=401, detail="Chave de cadastro inválida")
    body = await request.json()
    prof_id = body.get("id")
    ok = biometrics.delete_face_profile(prof_id)
    return JSONResponse(content={"success": ok})
