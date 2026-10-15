"""
Jarvis Biometrics & Multi-Operator Security Grid
Banco de Dados Relacional SQLite (auth/biometrics.db) + JSON Mirrors
Gerencia o banco de dados biométrico com descritores neurais 128D (FaceNet / ResNet-34),
logs de auditoria, portal dedicado de cadastro (12 dígitos) e chave mestre de emergência (16 dígitos).
"""

import os
import json
import time
import math
import sqlite3
from typing import Dict, Any, List, Optional

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(DIRECTORY, "auth")
DB_FILE = os.path.join(AUTH_DIR, "biometrics.db")
PROFILES_FILE = os.path.join(AUTH_DIR, "registered_faces.json")
WERIK_PROFILE_FILE = os.path.join(AUTH_DIR, "werik_face_profile.json")
PORTAL_STATE_FILE = os.path.join(AUTH_DIR, "portal_state.json")

# Variáveis de ambiente configuráveis via Docker / Sistema
ENROLLMENT_PORT = int(os.environ.get("ENROLLMENT_PORT", 8082))
ENROLLMENT_PORTAL_ENABLED_ENV = os.environ.get("ENROLLMENT_PORTAL_ENABLED", "true").lower() in ("true", "1", "yes")
ENROLLMENT_PASSWORD = str(os.environ.get("ENROLLMENT_PASSWORD", "")).strip()
MASTER_ACCESS_KEY = str(os.environ.get("MASTER_ACCESS_KEY", "")).strip()

os.makedirs(AUTH_DIR, exist_ok=True)

# ==============================================================================
# RBAC - Permissões por Operador (o Proprietário decide o que cada usuário pode)
# ==============================================================================
PERMISSION_FIELDS = [
    "full_access",       # Acesso total (equivale ao Proprietário)
    "chat",              # Conversar e fazer consultas ao Jarvis
    "voice_commands",    # Usar comandos de voz
    "media_control",     # Volume, música, play/pause, YouTube
    "windows_control",   # Janelas, aplicativos, teclado e mouse
    "clipboard",         # Área de transferência
    "screen_capture",    # Captura de tela / screenshots
    "power_control",     # Desligar / reiniciar / suspender / bloquear
    "infra_control",     # Docker, ZimaOS, containers, processos e SSH
    "finance_view",      # Dados bancários Pluggy e briefing financeiro
    "wake_on_lan",       # Ligar PCs remotamente (Wake-on-LAN)
]

OWNER_PERMISSIONS = {f: True for f in PERMISSION_FIELDS}

ROLE_PERMISSIONS = {
    "Proprietário": dict(OWNER_PERMISSIONS),
    "Operador Autorizado": {
        "full_access": False,
        "chat": True,
        "voice_commands": True,
        "media_control": True,
        "windows_control": False,
        "clipboard": False,
        "screen_capture": False,
        "power_control": False,
        "infra_control": False,
        "finance_view": False,
        "wake_on_lan": False,
    },
    "Convidado": {
        "full_access": False,
        "chat": True,
        "voice_commands": True,
        "media_control": False,
        "windows_control": False,
        "clipboard": False,
        "screen_capture": False,
        "power_control": False,
        "infra_control": False,
        "finance_view": False,
        "wake_on_lan": False,
    },
}

GUEST_PERMISSIONS = dict(ROLE_PERMISSIONS["Convidado"])


def resolve_permissions(role: str, stored=None) -> dict:
    """Resolve as permissões efetivas: padrão do papel mesclado com customizações salvas."""
    base = dict(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["Convidado"]))
    if isinstance(stored, dict):
        for k in PERMISSION_FIELDS:
            if k in stored:
                base[k] = bool(stored[k])
    if base.get("full_access"):
        return dict(OWNER_PERMISSIONS)
    return base


def init_db():
    """Inicializa as tabelas do Banco de Dados SQLite se não existirem."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operators (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Operador',
                descriptor TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                last_login TEXT,
                login_count INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                permissions TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                operator_name TEXT,
                distance REAL,
                confidence REAL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def _migrate_permissions_column():
    """Migra bancos antigos: adiciona a coluna permissions se ainda não existir."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(operators)").fetchall()]
            if "permissions" not in cols:
                conn.execute("ALTER TABLE operators ADD COLUMN permissions TEXT")
                conn.commit()
    except Exception as e:
        print(f"[Biometrics DB] Erro na migração da coluna permissions: {e}")

init_db()
_migrate_permissions_column()

def is_portal_enabled() -> bool:
    """Verifica se o portal de cadastro está ativo (via arquivo de estado dinâmico ou env var)."""
    if os.path.exists(PORTAL_STATE_FILE):
        try:
            with open(PORTAL_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return bool(data.get("enabled", True))
        except Exception:
            pass
    return ENROLLMENT_PORTAL_ENABLED_ENV

def set_portal_enabled(enabled: bool):
    """Ativa ou desativa dinamicamente o portal de cadastro facial."""
    with open(PORTAL_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"enabled": bool(enabled), "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=2)

def verify_enrollment_password(password: str) -> bool:
    """Valida a senha de 12 dígitos do portal de cadastro facial."""
    if not password:
        return False
    return str(password).strip() == ENROLLMENT_PASSWORD

def verify_master_key(key: str) -> bool:
    """Valida a chave mestre de 16 dígitos de emergência para desbloqueio do JARVIS HUD."""
    if not key:
        return False
    return str(key).strip() == MASTER_ACCESS_KEY

def get_registered_profiles() -> List[Dict[str, Any]]:
    """Carrega todos os operadores registrados diretamente do Banco de Dados SQLite."""
    profiles = []
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, role, descriptor, registered_at, last_login, login_count, permissions
                FROM operators 
                WHERE active = 1 
                ORDER BY registered_at ASC
            """)
            rows = cursor.fetchall()
            for r in rows:
                p_id, p_name, p_role, p_desc_str, p_reg, p_last, p_count, p_perms = r
                try:
                    desc_list = json.loads(p_desc_str)
                except Exception:
                    desc_list = []
                try:
                    stored_perms = json.loads(p_perms) if p_perms else None
                except Exception:
                    stored_perms = None
                profiles.append({
                    "id": p_id,
                    "name": p_name,
                    "role": p_role,
                    "registered_at": p_reg,
                    "last_login": p_last,
                    "login_count": p_count,
                    "descriptor": desc_list,
                    "stored_permissions": stored_perms,
                    "permissions": resolve_permissions(p_role, stored_perms)
                })
    except Exception as e:
        print(f"[Biometrics DB] Erro ao ler banco SQLite: {e}")

    # Fallback / Migração automática se SQLite estiver vazio mas houver JSON anterior
    if not profiles and os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                jdata = json.load(f)
                for p in jdata.get("profiles", []):
                    if p.get("descriptor"):
                        register_face_profile(p.get("name"), p.get("role", "Operador"), p.get("descriptor"))
            return get_registered_profiles()
        except Exception:
            pass

    return profiles

def sync_json_mirrors(profiles: List[Dict[str, Any]]):
    """Gera arquivos espelho em JSON para visualização externa e compatibilidade frontend."""
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump({"profiles": profiles, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=2)

        werik_prof = next((p for p in profiles if "werik" in p.get("name", "").lower() or p.get("id") == "werik"), None)
        if werik_prof:
            with open(WERIK_PROFILE_FILE, "w", encoding="utf-8") as wf:
                json.dump({
                    "registered": True,
                    "name": werik_prof.get("name", "Werik"),
                    "descriptor": werik_prof.get("descriptor"),
                    "registered_at": werik_prof.get("registered_at", time.strftime("%Y-%m-%d %H:%M:%S"))
                }, wf, indent=2)
    except Exception as e:
        print(f"[Biometrics] Erro ao sincronizar JSON mirrors: {e}")

def register_face_profile(name: str, role: str, descriptor: List[float], permissions: dict = None) -> Dict[str, Any]:
    """Salva um novo perfil biométrico com vetor neural 128D no banco SQLite e nos espelhos."""
    if not descriptor or len(descriptor) < 64:
        return {"success": False, "error": "Descritor neural inválido (esperado vetor 128D)."}

    clean_name = name.strip() or "Operador"
    prof_id = clean_name.lower().replace(" ", "_")
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    desc_json = json.dumps([float(x) for x in descriptor])
    perms_json = json.dumps(permissions) if isinstance(permissions, dict) else None

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("""
                INSERT INTO operators (id, name, role, descriptor, registered_at, active, permissions)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    role = excluded.role,
                    descriptor = excluded.descriptor,
                    registered_at = excluded.registered_at,
                    active = 1,
                    permissions = COALESCE(excluded.permissions, operators.permissions)
            """, (prof_id, clean_name, role.strip() or "Operador Autorizado", desc_json, now_str, perms_json))

            conn.execute("""
                INSERT INTO audit_logs (event_type, operator_name, distance, confidence, status, created_at)
                VALUES ('REGISTER_PROFILE', ?, 0.0, 1.0, 'SUCCESS', ?)
            """, (clean_name, now_str))
            conn.commit()

        # Atualiza espelhos JSON
        profiles = get_registered_profiles()
        sync_json_mirrors(profiles)
        print(f"[Biometrics DB] Perfil '{clean_name}' gravado no SQLite biometrics.db com sucesso! (Total ativos: {len(profiles)})")
        return {"success": True, "profile": {"id": prof_id, "name": clean_name, "role": role}}
    except Exception as e:
        print(f"[Biometrics DB] Erro ao gravar perfil no SQLite: {e}")
        return {"success": False, "error": str(e)}


def set_operator_permissions(profile_id: str, permissions: dict, role: str = None) -> Dict[str, Any]:
    """Define permissões customizadas (e opcionalmente o papel) de um operador. Reservado ao Proprietário."""
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    clean_perms = {}
    if isinstance(permissions, dict):
        for k in PERMISSION_FIELDS:
            if k in permissions:
                clean_perms[k] = bool(permissions[k])
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            if role:
                cur.execute("UPDATE operators SET role = ?, permissions = ? WHERE id = ? OR name = ?",
                            (role.strip(), json.dumps(clean_perms), profile_id, profile_id))
            else:
                cur.execute("UPDATE operators SET permissions = ? WHERE id = ? OR name = ?",
                            (json.dumps(clean_perms), profile_id, profile_id))
            updated = cur.rowcount or 0
            if not updated:
                return {"success": False, "error": f"Operador '{profile_id}' não encontrado."}
            conn.execute("""
                INSERT INTO audit_logs (event_type, operator_name, distance, confidence, status, created_at)
                VALUES ('PERMISSIONS_UPDATE', ?, 0.0, 1.0, 'SUCCESS', ?)
            """, (str(profile_id), now_str))
            conn.commit()

        profiles = get_registered_profiles()
        sync_json_mirrors(profiles)
        target = next((p for p in profiles if p.get("id") == profile_id or p.get("name") == profile_id), None)
        return {
            "success": True,
            "profile": {
                "id": target.get("id") if target else profile_id,
                "name": target.get("name") if target else profile_id,
                "role": (target or {}).get("role", role or ""),
                "permissions": (target or {}).get("permissions", resolve_permissions(role or "Convidado", clean_perms))
            }
        }
    except Exception as e:
        print(f"[Biometrics DB] Erro ao atualizar permissões: {e}")
        return {"success": False, "error": str(e)}

def delete_face_profile(profile_id: str) -> bool:
    """Remove ou desativa um operador no banco de dados SQLite."""
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("UPDATE operators SET active = 0 WHERE id = ? OR name = ?", (profile_id, profile_id))
            conn.execute("""
                INSERT INTO audit_logs (event_type, operator_name, distance, confidence, status, created_at)
                VALUES ('DELETE_PROFILE', ?, 0.0, 0.0, 'REMOVED', ?)
            """, (profile_id, now_str))
            conn.commit()

        profiles = get_registered_profiles()
        sync_json_mirrors(profiles)
        print(f"[Biometrics DB] Perfil '{profile_id}' desativado no SQLite.")
        return True
    except Exception as e:
        print(f"[Biometrics DB] Erro ao excluir operador: {e}")
        return False

def match_face_descriptor(client_descriptor: List[float], threshold: float = 0.48) -> Dict[str, Any]:
    """
    Compara o vetor neural de 128 dimensões da câmera com todos os operadores do SQLite.
    Se autenticado, atualiza login_count e last_login e gera log de auditoria.
    """
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    if not client_descriptor or len(client_descriptor) < 64:
        return {
            "authenticated": False,
            "reason": "INVALID_CLIENT_DESCRIPTOR",
            "confidence": 0.0,
            "user": None
        }

    profiles = get_registered_profiles()
    valid_profiles = [p for p in profiles if p.get("descriptor") and len(p["descriptor"]) >= 64]

    if not valid_profiles:
        return {
            "authenticated": False,
            "reason": "NO_PROFILES_REGISTERED",
            "confidence": 0.0,
            "user": None
        }

    best_match = None
    min_dist = float("inf")

    for prof in valid_profiles:
        saved_desc = prof["descriptor"]
        try:
            dist = math.sqrt(sum((float(a) - float(b))**2 for a, b in zip(client_descriptor, saved_desc)))
            if dist < min_dist:
                min_dist = dist
                best_match = prof
        except Exception:
            continue

    if best_match and min_dist < threshold:
        conf = round(max(0.0, min(1.0, 1.0 - (min_dist / 0.8))), 3)
        # Atualiza métricas no banco de dados SQLite
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("""
                    UPDATE operators 
                    SET login_count = login_count + 1, last_login = ? 
                    WHERE id = ?
                """, (now_str, best_match["id"]))
                conn.execute("""
                    INSERT INTO audit_logs (event_type, operator_name, distance, confidence, status, created_at)
                    VALUES ('LOGIN_SUCCESS', ?, ?, ?, 'AUTHENTICATED', ?)
                """, (best_match["name"], round(min_dist, 3), conf, now_str))
                conn.commit()
        except Exception as ed:
            print(f"[Biometrics DB] Erro ao registrar login audit: {ed}")

        return {
            "authenticated": True,
            "user": best_match["name"],
            "role": best_match.get("role", "Operador"),
            "permissions": best_match.get("permissions", GUEST_PERMISSIONS),
            "distance": round(min_dist, 3),
            "confidence": conf,
            "reason": "MATCH_CONFIRMED"
        }
    else:
        # Registra tentativa negada no log de auditoria
        try:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("""
                    INSERT INTO audit_logs (event_type, operator_name, distance, confidence, status, created_at)
                    VALUES ('LOGIN_DENIED', 'Desconhecido', ?, 0.0, 'STRANGER_DETECTED', ?)
                """, (round(min_dist, 3) if min_dist != float("inf") else 1.0, now_str))
                conn.commit()
        except Exception:
            pass

        return {
            "authenticated": False,
            "user": "Desconhecido",
            "distance": round(min_dist, 3) if min_dist != float("inf") else 1.0,
            "confidence": 0.0,
            "reason": "BIOMETRIC_MISMATCH_STRANGER"
        }
