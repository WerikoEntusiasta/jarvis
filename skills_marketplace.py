"""
J.A.R.V.I.S. Skills Marketplace Service
Integração e gerenciamento sob demanda de Skills do Hermes Agent e ClawHub Oficial.
Permite navegar pelo catálogo local e milhares de skills online no ClawHub,
visualizar documentação completa e instalar/desinstalar skills via UI sob demanda.
"""

import os
import re
import shutil
import json
import time
import logging
import urllib.request
import urllib.parse
import zipfile
import io
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None

try:
    import psycopg2
except ImportError:
    psycopg2 = None

try:
    import redis
except ImportError:
    redis = None

logger = logging.getLogger("JARVIS-MARKETPLACE")

def _resolve_dir(candidates, fallback):
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    p = Path(fallback)
    p.mkdir(parents=True, exist_ok=True)
    return p

HERMES_SKILLS_DIR = _resolve_dir([
    os.environ.get("HERMES_SKILLS_DIR", ""),
    "/app/skills/catalog_hermes",
    "/DATA/AppData/jarvis-hud/skills/catalog_hermes",
    "/DATA/AppData/hermes/home/skills",
    "c:/JARVIS/skills/catalog_hermes"
], "c:/JARVIS/skills/catalog_hermes")

ACTIVE_SKILLS_DIR = _resolve_dir([
    os.environ.get("JARVIS_ACTIVE_SKILLS_DIR", ""),
    "/app/skills/active",
    "/DATA/AppData/jarvis-hud/skills/active",
    "c:/JARVIS/skills/active"
], "c:/JARVIS/skills/active")

PG_HOST = os.environ.get("PG_HOST", "172.17.0.11")
PG_PORT = int(os.environ.get("PG_PORT", 5432))
PG_USER = os.environ.get("PG_USER", "casaos")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "Casaos_Db_Sec2026!")
PG_DATABASE = os.environ.get("PG_DATABASE", "jarvis_memory")

CLAWHUB_API_BASE = "https://clawhub.ai/api/v1"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) JARVIS-Hub/2.0"

# Cache em memória para requisições ClawHub (TTL: 15 minutos)
_CACHE = {}
_CACHE_TTL = 900  # 15 minutos


def _cache_get(key: str) -> Optional[Any]:
    entry = _CACHE.get(key)
    if entry:
        val, ts = entry
        if time.time() - ts < _CACHE_TTL:
            return val
    return None


def _cache_set(key: str, val: Any):
    _CACHE[key] = (val, time.time())


def _parse_frontmatter(content: str) -> Tuple[dict, str]:
    """Extrai cabeçalho YAML e corpo Markdown de um arquivo SKILL.md."""
    frontmatter = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_yaml = parts[1].strip()
            body = parts[2].strip()
            if yaml:
                try:
                    frontmatter = yaml.safe_load(raw_yaml) or {}
                except Exception:
                    pass
            else:
                for line in raw_yaml.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        frontmatter[k.strip()] = v.strip().strip('"').strip("'")
    return frontmatter, body


def _get_installed_skill_ids() -> set:
    """Retorna conjunto de IDs de skills instaladas a partir do banco e do disco."""
    installed = set()
    
    if ACTIVE_SKILLS_DIR.exists():
        for d in ACTIVE_SKILLS_DIR.iterdir():
            if d.is_dir():
                installed.add(d.name)

    try:
        if psycopg2:
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DATABASE, connect_timeout=1
            )
            cur = conn.cursor()
            cur.execute("SELECT id FROM jarvis_skills WHERE status = 'installed';")
            for r in cur.fetchall():
                installed.add(r[0])
            cur.close()
            conn.close()
    except Exception as e:
        logger.warning("[DB-SKILLS] Erro ao consultar instaladas: %s", e)

    return installed


def _load_local_hermes_skills() -> List[Dict[str, Any]]:
    """Carrega o catálogo local do Hermes Agent."""
    skills = []
    if not HERMES_SKILLS_DIR.exists():
        return skills

    installed_ids = _get_installed_skill_ids()

    for skill_md in HERMES_SKILLS_DIR.glob("**/SKILL.md"):
        try:
            skill_dir = skill_md.parent
            skill_id = skill_dir.name
            rel_parts = skill_dir.relative_to(HERMES_SKILLS_DIR).parts
            cat = "geral"
            for part in rel_parts:
                if part not in ["skills", "catalog_hermes", skill_id]:
                    cat = part
                    break

            with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            fm, _ = _parse_frontmatter(content)
            name = fm.get("name", skill_id.replace("-", " ").title())
            desc = fm.get("description", "")
            if not desc:
                for p in content.split("\n\n"):
                    if p.strip() and not p.startswith("#") and not p.startswith("---"):
                        desc = p.strip()[:200]
                        break

            meta = fm.get("metadata", {})
            hermes_meta = meta.get("hermes", {}) if isinstance(meta, dict) else {}
            tags = hermes_meta.get("tags", [cat, "Hermes"])
            author = fm.get("author", "Nous Research & Community")
            version = str(fm.get("version", "1.0.0"))

            skills.append({
                "id": skill_id,
                "name": name,
                "source": "Hermes Hub",
                "category": cat,
                "description": desc or f"Skill especializada em {name}.",
                "tags": tags if isinstance(tags, list) else [str(tags)],
                "author": author,
                "version": version,
                "installed": skill_id in installed_ids,
                "downloads": 1000,
                "stars": 50,
                "local_path": str(skill_dir)
            })
        except Exception as ex:
            logger.debug("Erro ao ler skill local %s: %s", skill_md, ex)

    return skills


def fetch_clawhub_skills(cursor: Optional[str] = None, limit: int = 30) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Busca página de skills diretamente da API oficial do ClawHub."""
    cache_key = f"clawhub:skills:limit={limit}:cursor={cursor or ''}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    url = f"{CLAWHUB_API_BASE}/skills?limit={limit}"
    if cursor:
        url += f"&cursor={urllib.parse.quote(cursor)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items", [])
            next_cursor = data.get("nextCursor")

            installed_ids = _get_installed_skill_ids()
            results = []
            for it in items:
                owner = it.get("ownerHandle") or "community"
                slug = it.get("slug") or ""
                skill_id = f"clawhub:{owner}/{slug}"
                topics = it.get("topics") or []
                cat = topics[0] if topics else "clawhub"
                tags = list(topics) + ["ClawHub", owner]
                stats = it.get("stats") or {}
                ver_info = it.get("latestVersion") or {}

                results.append({
                    "id": skill_id,
                    "slug": slug,
                    "owner": owner,
                    "name": it.get("displayName") or slug.replace("-", " ").title(),
                    "source": "ClawHub",
                    "category": cat,
                    "description": it.get("summary") or "Habilidade oficial da comunidade ClawHub.",
                    "tags": tags,
                    "author": owner,
                    "version": ver_info.get("version", "1.0.0"),
                    "downloads": stats.get("downloads", 0),
                    "stars": stats.get("stars", 0),
                    "installed": skill_id in installed_ids
                })

            ret = (results, next_cursor)
            _cache_set(cache_key, ret)
            return ret
    except Exception as e:
        logger.warning("[CLAWHUB] Erro ao listar skills do ClawHub: %s", e)
        return [], None


def search_clawhub_skills(query: str) -> List[Dict[str, Any]]:
    """Pesquisa no índice público completo do ClawHub (milhares de skills)."""
    if not query:
        return []

    cache_key = f"clawhub:search:{query.lower().strip()}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    url = f"{CLAWHUB_API_BASE}/search?q={urllib.parse.quote(query.strip())}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_results = data.get("results", [])

            installed_ids = _get_installed_skill_ids()
            skills = []
            for r in raw_results:
                owner = r.get("ownerHandle") or "clawhub"
                slug = r.get("slug") or ""
                skill_id = f"clawhub:{owner}/{slug}"
                
                native_skill = r.get("native", {}).get("skill", {})
                cats = native_skill.get("categories") or ["clawhub"]
                cat = cats[0] if cats else "clawhub"
                topics = native_skill.get("topics") or []
                tags = list(topics) + ["ClawHub", owner]
                stats = native_skill.get("stats") or {}

                skills.append({
                    "id": skill_id,
                    "slug": slug,
                    "owner": owner,
                    "name": r.get("displayName") or slug.replace("-", " ").title(),
                    "source": "ClawHub",
                    "category": cat,
                    "description": r.get("summary") or "Habilidade oficial da comunidade ClawHub.",
                    "tags": tags,
                    "author": owner,
                    "version": native_skill.get("tags", {}).get("latest", "1.0.0"),
                    "downloads": r.get("downloads", 0),
                    "stars": stats.get("stars", 0),
                    "installed": skill_id in installed_ids
                })

            _cache_set(cache_key, skills)
            return skills
    except Exception as e:
        logger.warning("[CLAWHUB] Erro ao pesquisar no ClawHub: %s", e)
        return []


def list_marketplace_skills(
    search: str = "",
    category: str = "",
    status: str = "",
    source: str = "all",
    cursor: str = "",
    limit: int = 30
) -> Dict[str, Any]:
    """Retorna lista de skills agregada: Hermes Hub e milhares de skills do ClawHub."""
    s_query = (search or "").strip()
    c_query = (category or "").lower().strip()
    st_query = (status or "").lower().strip()
    src_query = (source or "all").lower().strip()

    skills = []
    next_cursor = None

    # 1. Carrega skills do Hermes Agent (local)
    hermes_skills = []
    if src_query in ["all", "hermes"]:
        hermes_skills = _load_local_hermes_skills()

    # 2. Carrega skills do ClawHub Oficial
    clawhub_skills = []
    if src_query in ["all", "clawhub"]:
        if s_query:
            clawhub_skills = search_clawhub_skills(s_query)
        else:
            clawhub_skills, next_cursor = fetch_clawhub_skills(cursor=cursor, limit=limit)

    # 3. Combina conforme filtro de busca se local também for incluído
    if s_query and src_query in ["all", "hermes"]:
        q_low = s_query.lower()
        hermes_filtered = []
        for s in hermes_skills:
            in_name = q_low in s["name"].lower()
            in_desc = q_low in s["description"].lower()
            in_tags = any(q_low in t.lower() for t in s["tags"])
            if in_name or in_desc or in_tags:
                hermes_filtered.append(s)
        hermes_skills = hermes_filtered

    # Unifica
    if src_query == "hermes":
        skills = hermes_skills
    elif src_query == "clawhub":
        skills = clawhub_skills
    else:
        # "all": coloca primeiro instaladas, depois Hermes, depois ClawHub
        skills = hermes_skills + clawhub_skills

    # 4. Aplica filtros de categoria e status
    filtered = []
    for s in skills:
        if c_query and c_query != "todos" and s["category"].lower() != c_query:
            continue
        if st_query == "installed" and not s["installed"]:
            continue
        if st_query == "available" and s["installed"]:
            continue
        filtered.append(s)

    # Ordena: instaladas primeiro, depois por popularidade/nome
    filtered.sort(key=lambda s: (not s.get("installed", False), -s.get("downloads", 0), s.get("name", "")))

    return {
        "skills": filtered,
        "next_cursor": next_cursor,
        "total": len(filtered),
        "total_hermes": len(hermes_skills),
        "total_clawhub": "Milhares online no ClawHub"
    }


def get_skill_details(skill_id: str) -> Optional[Dict[str, Any]]:
    """Recupera metadados completos e o conteúdo do SKILL.md (Hermes ou ClawHub)."""
    installed_ids = _get_installed_skill_ids()

    # 1. Procura em Hermes Skills (local)
    if HERMES_SKILLS_DIR.exists():
        for skill_md in HERMES_SKILLS_DIR.glob(f"**/{skill_id}/SKILL.md"):
            try:
                with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                fm, body = _parse_frontmatter(content)
                return {
                    "id": skill_id,
                    "name": fm.get("name", skill_id.replace("-", " ").title()),
                    "source": "Hermes Hub",
                    "category": skill_md.parent.parent.name,
                    "description": fm.get("description", ""),
                    "author": fm.get("author", "Nous Research"),
                    "version": str(fm.get("version", "1.0.0")),
                    "installed": skill_id in installed_ids,
                    "readme": content,
                    "markdown_body": body
                }
            except Exception as e:
                logger.error("Erro lendo skill local %s: %s", skill_id, e)

    # 2. Se for do ClawHub (clawhub:owner/slug)
    if skill_id.startswith("clawhub:"):
        ref = skill_id.replace("clawhub:", "")
        owner, slug = ref.split("/", 1) if "/" in ref else ("", ref)
        
        # Baixa o pacote zip para ler o SKILL.md oficial
        dl_url = f"{CLAWHUB_API_BASE}/download?slug={urllib.parse.quote(slug)}"
        if owner:
            dl_url += f"&ownerHandle={urllib.parse.quote(owner)}"

        try:
            req = urllib.request.Request(dl_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=10) as resp:
                zip_bytes = resp.read()
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                    readme_content = ""
                    # Procura SKILL.md ou skill-card.md
                    for fname in ["SKILL.md", "skill-card.md", "README.md"]:
                        for zf in z.namelist():
                            if zf.endswith(fname):
                                readme_content = z.read(zf).decode("utf-8", errors="replace")
                                break
                        if readme_content:
                            break

                    fm, body = _parse_frontmatter(readme_content)
                    return {
                        "id": skill_id,
                        "slug": slug,
                        "owner": owner,
                        "name": fm.get("name", slug.replace("-", " ").title()),
                        "source": "ClawHub",
                        "category": "clawhub",
                        "description": fm.get("description", "Habilidade da comunidade ClawHub."),
                        "author": owner,
                        "version": str(fm.get("version", "1.0.0")),
                        "installed": skill_id in installed_ids,
                        "readme": readme_content or f"# {slug}\n\nSkill baixada sob demanda do ClawHub.",
                        "markdown_body": body or readme_content
                    }
        except Exception as ex:
            logger.error("Erro ao obter documentação da skill ClawHub %s: %s", skill_id, ex)
            return {
                "id": skill_id,
                "name": slug.replace("-", " ").title(),
                "source": "ClawHub",
                "category": "clawhub",
                "description": f"Skill {slug} da comunidade ClawHub.",
                "author": owner,
                "version": "1.0.0",
                "installed": skill_id in installed_ids,
                "readme": f"# {slug}\n\nDocumentação não pôde ser recuperada: {ex}",
                "markdown_body": str(ex)
            }

    return None


def install_skill(skill_id: str) -> Dict[str, Any]:
    """Instala uma skill sob demanda no diretório ativo do JARVIS e registra no PostgreSQL."""
    ACTIVE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    clean_id = skill_id.replace("clawhub:", "").replace("/", "_")
    target_dir = ACTIVE_SKILLS_DIR / clean_id

    details = get_skill_details(skill_id)
    if not details:
        return {"success": False, "error": f"Skill '{skill_id}' não encontrada no Marketplace."}

    # Caso 1: Skill local Hermes Agent
    source_found = False
    if HERMES_SKILLS_DIR.exists():
        for sdir in HERMES_SKILLS_DIR.glob(f"**/{skill_id}"):
            if sdir.is_dir() and (sdir / "SKILL.md").exists():
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.copytree(sdir, target_dir)
                source_found = True
                break

    # Caso 2: Skill online do ClawHub
    if not source_found and skill_id.startswith("clawhub:"):
        ref = skill_id.replace("clawhub:", "")
        owner, slug = ref.split("/", 1) if "/" in ref else ("", ref)
        dl_url = f"{CLAWHUB_API_BASE}/download?slug={urllib.parse.quote(slug)}"
        if owner:
            dl_url += f"&ownerHandle={urllib.parse.quote(owner)}"

        try:
            req = urllib.request.Request(dl_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                zip_bytes = resp.read()
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                    z.extractall(target_dir)
                source_found = True
        except Exception as e:
            logger.error("Erro baixando skill do ClawHub: %s", e)
            return {"success": False, "error": f"Falha ao baixar skill do ClawHub: {e}"}

    # Fallback se apenas metadados foram obtidos
    if not source_found:
        target_dir.mkdir(parents=True, exist_ok=True)
        with open(target_dir / "SKILL.md", "w", encoding="utf-8") as f:
            f.write(details.get("readme", f"# {details['name']}\n\n{details['description']}"))

    # Registra no PostgreSQL
    try:
        if psycopg2:
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DATABASE, connect_timeout=2
            )
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO jarvis_skills (id, name, source, category, description, tags, status, installed_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'installed', NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    status = 'installed',
                    installed_at = NOW(),
                    updated_at = NOW();
                """,
                (
                    skill_id,
                    details["name"],
                    details["source"],
                    details["category"],
                    details["description"],
                    json.dumps(details.get("tags", []))
                )
            )
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        logger.warning("[DB-INSTALL] Falha ao registrar no Postgres: %s", e)

    logger.info("[MARKETPLACE] Skill '%s' instalada com sucesso!", skill_id)
    return {
        "success": True,
        "message": f"Skill '{details['name']}' instalada sob demanda com sucesso no J.A.R.V.I.S.!",
        "skill": details
    }


def uninstall_skill(skill_id: str) -> Dict[str, Any]:
    """Desinstala uma skill do J.A.R.V.I.S. e atualiza o status para available no banco."""
    clean_id = skill_id.replace("clawhub:", "").replace("/", "_")
    for tid in [clean_id, skill_id]:
        target_dir = ACTIVE_SKILLS_DIR / tid
        if target_dir.exists():
            try:
                shutil.rmtree(target_dir)
            except Exception as e:
                logger.error("Erro ao remover diretório da skill %s: %s", tid, e)

    # Atualiza no PostgreSQL
    try:
        if psycopg2:
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DATABASE, connect_timeout=2
            )
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE jarvis_skills 
                SET status = 'available', updated_at = NOW()
                WHERE id = %s;
                """,
                (skill_id,)
            )
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        logger.warning("[DB-UNINSTALL] Falha ao atualizar no Postgres: %s", e)

    logger.info("[MARKETPLACE] Skill '%s' desinstalada.", skill_id)
    return {
        "success": True,
        "message": f"Skill '{skill_id}' removida do J.A.R.V.I.S. com sucesso."
    }
