"""
J.A.R.V.I.S. — Self-Evolution & Autonomous Engineering Subsystem
Permite que o J.A.R.V.I.S. auto-inspecione, modifique, teste, sincronize com o GitHub
e recarregue seus próprios componentes e telas autonomamente a pedido do Senhor Werik.
"""

import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("JarvisSelfEvolution")
REPO_ROOT = Path(__file__).resolve().parent

def get_repo_root() -> Path:
    return REPO_ROOT

def self_read_code(file_path: str, start_line: int = 1, end_line: int = 500) -> Dict[str, Any]:
    """Lê trechos de código do repositório do JARVIS."""
    try:
        path = (REPO_ROOT / file_path).resolve()
        if not path.is_relative_to(REPO_ROOT) and not str(path).startswith(str(REPO_ROOT)):
            return {"ok": False, "error": "Acesso restrito ao repositório do JARVIS."}
        if not path.exists():
            return {"ok": False, "error": f"Arquivo não encontrado: {file_path}"}
        
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        s = max(1, start_line) - 1
        e = min(total_lines, end_line)
        snippet = "".join(lines[s:e])
        
        return {
            "ok": True,
            "file": file_path,
            "total_lines": total_lines,
            "start_line": s + 1,
            "end_line": e,
            "content": snippet
        }
    except Exception as ex:
        logger.error(f"[SelfEvolution] Erro ao ler {file_path}: {ex}")
        return {"ok": False, "error": str(ex)}

def self_modify_code(file_path: str, search_target: str, replacement: str) -> Dict[str, Any]:
    """Substitui um bloco específico de código dentro de um arquivo do JARVIS."""
    try:
        path = (REPO_ROOT / file_path).resolve()
        if not path.exists():
            return {"ok": False, "error": f"Arquivo não encontrado: {file_path}"}
        
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        if search_target not in content:
            # Tenta normalização de quebras de linha
            norm_content = content.replace("\r\n", "\n")
            norm_target = search_target.replace("\r\n", "\n")
            if norm_target in norm_content:
                norm_replacement = replacement.replace("\r\n", "\n")
                new_content = norm_content.replace(norm_target, norm_replacement, 1)
            else:
                return {"ok": False, "error": "Trecho alvo não encontrado no arquivo para substituição."}
        else:
            new_content = content.replace(search_target, replacement, 1)
            
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        logger.info(f"[SelfEvolution] Arquivo modificado com sucesso: {file_path}")
        return {"ok": True, "file": file_path, "message": "Código modificado com sucesso."}
    except Exception as ex:
        logger.error(f"[SelfEvolution] Erro ao modificar {file_path}: {ex}")
        return {"ok": False, "error": str(ex)}

def self_write_code(file_path: str, content: str) -> Dict[str, Any]:
    """Cria ou sobrescreve um arquivo de código no repositório do JARVIS."""
    try:
        path = (REPO_ROOT / file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "file": file_path, "bytes_written": len(content)}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}

def self_git_status() -> Dict[str, Any]:
    """Retorna o status atual do git no repositório central."""
    try:
        res = subprocess.run(["git", "status", "-s"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        return {"ok": True, "status": res.stdout.strip()}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}

def self_git_sync(commit_message: str = "auto: J.A.R.V.I.S. self-evolution update") -> Dict[str, Any]:
    """Faz commit das alterações locais e push diretamente para o GitHub oficial na branch ativa."""
    try:
        subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=True, timeout=15)
        commit_res = subprocess.run(["git", "commit", "-m", commit_message], cwd=REPO_ROOT, capture_output=True, text=True, timeout=15)
        push_res = subprocess.run(["git", "push", "origin", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
        
        ok = push_res.returncode == 0
        return {
            "ok": ok,
            "commit_output": commit_res.stdout.strip() or commit_res.stderr.strip(),
            "push_output": push_res.stdout.strip() or push_res.stderr.strip(),
            "message": "Sincronizado com o GitHub com sucesso!" if ok else "Falha no envio ao GitHub."
        }
    except Exception as ex:
        logger.error(f"[SelfEvolution] Falha git sync: {ex}")
        return {"ok": False, "error": str(ex)}

def self_git_pull() -> Dict[str, Any]:
    """Puxa as últimas atualizações feitas por outras IAs ou por você no GitHub."""
    try:
        res = subprocess.run(["git", "pull", "origin", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
        return {"ok": res.returncode == 0, "output": res.stdout.strip() or res.stderr.strip()}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}

def self_reload_hud() -> Dict[str, Any]:
    """Recarrega a interface webview do Windows para aplicar alterações instantaneamente."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        s.connect(("127.0.0.1", 49160))
        s.sendall(b"RELOAD\n")
        s.close()
        return {"ok": True, "message": "HUD recarregado com sucesso via IPC na porta 49160."}
    except Exception as ex_ipc:
        try:
            from core.local_server import broadcast_hud_event
            broadcast_hud_event("command", {"action": "reload"})
            return {"ok": True, "message": "Comando de recarregamento transmitido via SSE."}
        except Exception as ex_sse:
            return {"ok": False, "error": f"Falha ao recarregar HUD: {ex_ipc} / {ex_sse}"}
