"""
J.A.R.V.I.S. Obsidian Manager (Terceiro Cérebro & Aprendizado Contínuo)
Integração nativa com o Vault Obsidian oficial do Senhor Werik.
Permite pesquisa, leitura, escrita e registro estruturado de erros e aprendizados.
Padrão Permanente de Engenharia de Software Sênior.
"""

import os
import sys
import glob
import re
import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ObsidianManager")
logger.setLevel(logging.INFO)

# Caminhos padrão do Vault do Terceiro Cérebro
VAULT_CANDIDATES = [
    r"Z:\Terceiro_Cerebro",                                    # Mapeamento oficial Windows (Samba ZimaOS)
    "/DATA/Terceiro_Cerebro",                                  # Caminho nativo no ZimaOS Host
    "/DATA/AppData/obsidian/config/Terceiro_Cerebro",          # Caminho do container linuxserver-obsidian
    os.path.join(os.path.expanduser("~"), "Terceiro_Cerebro"), # Fallback Home do Usuário
    os.path.abspath(os.path.join(os.path.dirname(__file__), "terceiro_cerebro")) # Fallback local JARVIS
]


def get_vault_path() -> Optional[str]:
    """Retorna o caminho raiz acessível do cofre do Obsidian."""
    for p in VAULT_CANDIDATES:
        try:
            if os.path.isdir(p):
                return os.path.abspath(p)
        except Exception:
            continue
    # Se nenhum existir mas estivermos no Windows e Z: não estiver montado, tenta criar o fallback local
    fallback = VAULT_CANDIDATES[-1]
    try:
        os.makedirs(fallback, exist_ok=True)
        return fallback
    except Exception:
        return None


def get_learning_note_path() -> str:
    """Retorna o caminho absoluto da nota dedicada ao aprendizado e histórico de erros."""
    vault = get_vault_path()
    if not vault:
        raise RuntimeError("Cofre do Obsidian indisponível.")
    target_dir = os.path.join(vault, "05_MEMORIA_AGENTES")
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, "JARVIS_APRENDIZADO.md")


def _init_learning_file_if_needed(file_path: str):
    """Inicializa o arquivo de aprendizado com cabeçalho caso ainda não exista."""
    if not os.path.exists(file_path):
        header = """# 🧠 JARVIS_APRENDIZADO.md — Memória de Aprendizado Contínuo com Erros & Sucessos
*Vault Terceiro Cérebro | J.A.R.V.I.S. Core*

> [!NOTE]
> Este documento registra todos os erros operacionais encontrados no Windows, automações, coordenadas,
> atalhos e comportamentos de janelas, acompanhados da respectiva **solução que funcionou** e da **regra aprendida**.
> **O J.A.R.V.I.S. deve sempre consultar esta nota antes de ações críticas para não repetir falhas anteriores.**

---

## 📚 REGISTROS DE APRENDIZADO & CORREÇÃO

"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(header)


# ==============================================================================
# 1. PESQUISA NO OBSIDIAN (BUSCA EM CONTEÚDO E TÍTULOS)
# ==============================================================================

def obsidian_search_notes(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Pesquisa palavras-chave ou frases em todas as notas markdown do cofre Obsidian.
    Retorna títulos, caminhos relativos e trechos contextuais.
    """
    vault = get_vault_path()
    if not vault:
        return {"ok": False, "erro": "Cofre do Obsidian não encontrado"}

    q_lower = (query or "").lower().strip()
    if not q_lower:
        return {"ok": False, "erro": "Termo de busca vazio"}

    matches = []
    ignored_dirs = {".obsidian", ".trash", ".git", "node_modules"}

    try:
        for root, dirs, files in os.walk(vault):
            dirs[:] = [d for d in dirs if d not in ignored_dirs]
            for file in files:
                if not file.lower().endswith(".md"):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, vault).replace("\\", "/")

                title_match = q_lower in file.lower()
                content_snippets = []

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines):
                        if q_lower in line.lower():
                            start_l = max(0, idx - 1)
                            end_l = min(len(lines), idx + 2)
                            snippet = "".join(lines[start_l:end_l]).strip()
                            content_snippets.append(snippet)
                            if len(content_snippets) >= 2:
                                break
                except Exception:
                    pass

                if title_match or content_snippets:
                    matches.append({
                        "file": file,
                        "relative_path": rel_path,
                        "title_matched": title_match,
                        "snippets": content_snippets[:2]
                    })
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break

        return {
            "ok": True,
            "query": query,
            "vault": vault,
            "count": len(matches),
            "results": matches
        }
    except Exception as e:
        return {"ok": False, "erro": str(e)}


# ==============================================================================
# 2. LEITURA DE NOTA COMPLETA
# ==============================================================================

def obsidian_read_note(relative_path: str, max_lines: int = 250) -> Dict[str, Any]:
    """
    Lê o conteúdo de uma nota markdown no cofre do Obsidian pelo caminho relativo.
    Exemplo: '05_MEMORIA_AGENTES/SHARED_CONTEXT.md' ou '05_MEMORIA_AGENTES/JARVIS_APRENDIZADO.md'.
    """
    vault = get_vault_path()
    if not vault:
        return {"ok": False, "erro": "Cofre do Obsidian não encontrado"}

    # Normaliza caminho
    clean_rel = relative_path.strip().lstrip("/\\")
    if not clean_rel.lower().endswith(".md"):
        clean_rel += ".md"

    full_path = os.path.join(vault, clean_rel)
    if not os.path.exists(full_path):
        # Tenta buscar em subpastas caso tenha passado apenas o nome do arquivo
        file_name = os.path.basename(clean_rel)
        found = None
        for root, _, files in os.walk(vault):
            if file_name in files:
                found = os.path.join(root, file_name)
                clean_rel = os.path.relpath(found, vault).replace("\\", "/")
                break
        if found:
            full_path = found
        else:
            return {"ok": False, "erro": f"Nota não encontrada: {relative_path}"}

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        truncated = len(lines) > max_lines
        content = "".join(lines[:max_lines])

        return {
            "ok": True,
            "relative_path": clean_rel,
            "full_path": full_path,
            "lines_read": min(len(lines), max_lines),
            "total_lines": len(lines),
            "truncated": truncated,
            "content": content
        }
    except Exception as e:
        return {"ok": False, "erro": str(e)}


# ==============================================================================
# 3. APRENDIZADO CONTÍNUO (REGISTRO DE ERROS E SOLUÇÕES)
# ==============================================================================

def obsidian_append_learning(topic: str, error_encountered: str, solution_applied: str, context: str = "") -> Dict[str, Any]:
    """
    Grava uma nova entrada de aprendizado no Terceiro Cérebro em '05_MEMORIA_AGENTES/JARVIS_APRENDIZADO.md'.
    Registra o que deu errado, como foi corrigido e a regra que deve ser seguida no futuro.
    """
    vault = get_vault_path()
    if not vault:
        return {"ok": False, "erro": "Cofre do Obsidian não encontrado"}

    try:
        learning_path = get_learning_note_path()
        _init_learning_file_if_needed(learning_path)

        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        entry = f"""### [{now_str}] | Tópico: {topic.strip()}
- **Contexto / Solicitação:** {context.strip() or "Operação no sistema Windows pelo J.A.R.V.I.S."}
- **Falha / Erro Observado:** {error_encountered.strip()}
- **Solução / Ação Efetiva:** {solution_applied.strip()}
- **Regra Aprendida para as Próximas Vezes:** Sempre aplicar a solução acima e validar via captura de tela (`take_screenshot`).
- **Tags:** #aprendizado #jarvis #correcao #auto_evolucao

---

"""
        with open(learning_path, "a", encoding="utf-8") as f:
            f.write(entry)

        return {
            "ok": True,
            "action": "obsidian_append_learning",
            "file": "05_MEMORIA_AGENTES/JARVIS_APRENDIZADO.md",
            "timestamp": now_str,
            "topic": topic
        }
    except Exception as e:
        logger.error(f"Erro ao gravar aprendizado no Obsidian: {e}")
        return {"ok": False, "erro": str(e)}


# ==============================================================================
# 4. ESCRITA OU CRIAÇÃO DE NOTAS GERAIS NO OBSIDIAN
# ==============================================================================

def obsidian_write_note(relative_path: str, content: str, mode: str = "append") -> Dict[str, Any]:
    """
    Cria ou atualiza uma nota markdown no cofre do Obsidian.
    mode: 'append' (adiciona ao fim) ou 'overwrite' (substitui todo o conteúdo).
    """
    vault = get_vault_path()
    if not vault:
        return {"ok": False, "erro": "Cofre do Obsidian não encontrado"}

    clean_rel = relative_path.strip().lstrip("/\\")
    if not clean_rel.lower().endswith(".md"):
        clean_rel += ".md"

    full_path = os.path.join(vault, clean_rel)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    try:
        write_mode = "a" if mode.lower() == "append" else "w"
        prefix = "\n\n" if mode.lower() == "append" and os.path.exists(full_path) else ""
        with open(full_path, write_mode, encoding="utf-8") as f:
            f.write(prefix + content.strip() + "\n")

        return {
            "ok": True,
            "action": "obsidian_write_note",
            "relative_path": clean_rel,
            "mode": mode,
            "bytes_written": len(content.encode("utf-8"))
        }
    except Exception as e:
        return {"ok": False, "erro": str(e)}
