"""
J.A.R.V.I.S. — Web Intelligence (SearXNG + Crawl4ai no ZimaOS)
=========================================================================
- web_search : busca privada agregada (Google/Bing/DDG...) via SearXNG em JSON
- read_url   : converte qualquer pagina em Markdown limpo via Crawl4ai

Infraestrutura self-hosted no ZimaOS (docker agent-infra):
  - SearXNG   http://<zima>:8890  (busca JSON, sem chave)
  - Crawl4ai  http://<zima>:11235 (token fixo)

Sem API key publica, sem rate limit de terceiros, sem rastreio.
"""

import json
import time
import logging
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional

logger = logging.getLogger("WebIntel")

# Endpoints do ZimaOS. IP publico funciona de qualquer lugar; o ZeroTier
# (10.147.20.1) e o fallback local do proprio Zima.
SEARXNG_URL = "http://45.167.187.80:8890"
CRAWL4AI_URL = "http://45.167.187.80:11235"
CRAWL4AI_TOKEN = "jarvis-crawl4ai-zimaos-2026"

_CACHE: Dict[str, tuple] = {}
_CACHE_TTL = 300.0  # 5 min


def _cached(key: str):
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    return None


def _put(key: str, value):
    _CACHE[key] = (time.time(), value)
    return value


def _http(url: str, payload: Optional[Dict[str, Any]] = None,
          timeout: int = 45, token: str = "") -> bytes:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"User-Agent": "JARVIS/1.0", "Accept": "application/json"}
    if data is not None:
        # Sem isto o urllib usa x-www-form-urlencoded e o servidor
        # recebe o JSON como string (HTTP 422).
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def web_search(query: str, limite: int = 8, language: str = "pt-BR") -> Dict[str, Any]:
    """Busca web privada via SearXNG. Retorna resultados estruturados.

    Returns: {ok, query, results: [{title, url, content, source}], summary}
    """
    query = str(query or "").strip()
    if not query:
        return {"ok": False, "error": "query vazia"}
    limite = max(1, min(20, int(limite or 8)))

    key = f"search:{query.lower()}:{limite}:{language}"
    hit = _cached(key)
    if hit is not None:
        return hit

    qs = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "language": language,
        "safesearch": 0,
    })
    try:
        raw = _http(f"{SEARXNG_URL}/search?{qs}", timeout=45)
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        logger.warning(f"[WebIntel] SearXNG falhou para '{query}': {e}")
        return {"ok": False, "error": f"busca indisponivel: {type(e).__name__}"}

    results: List[Dict[str, Any]] = []
    seen = set()
    for r in data.get("results") or []:
        if len(results) >= limite:
            break
        url = r.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({
            "title": (r.get("title") or "").strip(),
            "url": url,
            "content": (r.get("content") or "").strip()[:500],
            "source": (r.get("source") or urllib.parse.urlparse(url).netloc or ""),
            "published": (r.get("publishedDate") or "")[:40],
        })

    if not results:
        return {"ok": False, "error": f"nenhum resultado para '{query}'"}

    resumo = "Resultados: " + "; ".join(r["title"].lower().rstrip(".") for r in results[:3])
    return _put(key, {
        "ok": True,
        "query": query,
        "results": results,
        "summary": resumo,
        "engine": "SearXNG (self-hosted)",
    })


def read_url(url: str, limite: int = 12000,
             selector: str = "") -> Dict[str, Any]:
    """Extrai uma pagina como Markdown limpo via Crawl4ai.

    Args:
        url: pagina completa (http/https)
        limite: max de caracteres do markdown devolvido
        selector: CSS selector opcional p/ extrair so uma regiao
    Returns: {ok, url, markdown, title, length}
    """
    url = str(url or "").strip()
    if not url:
        return {"ok": False, "error": "url vazia"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    limite = max(500, min(50000, int(limite or 12000)))

    key = f"read:{url}:{limite}:{selector}"
    hit = _cached(key)
    if hit is not None:
        return hit

    payload: Dict[str, Any] = {
        "urls": [url],
        "exclude_tags": ["script", "style", "nav", "footer", "iframe"],
        "exclude_external_links": True,
        "wait_for": "body",
    }
    if selector:
        payload["css_selector"] = selector

    try:
        raw = _http(f"{CRAWL4AI_URL}/crawl", payload=payload,
                    timeout=90, token=CRAWL4AI_TOKEN)
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as e:
        logger.warning(f"[WebIntel] Crawl4ai falhou para '{url}': {e}")
        return {"ok": False, "error": f"leitura indisponivel: {type(e).__name__}"}

    results = data.get("results") or []
    if not results:
        err = data.get("error") or data.get("message") or "sem conteudo"
        return {"ok": False, "error": f"crawl falhou: {str(err)[:200]}"}

    first = results[0]
    md = first.get("markdown") or ""
    if isinstance(md, dict):
        md = md.get("raw_markdown") or md.get("markdown") or md.get("fit_markdown") or ""
    md = str(md).strip()
    title = str(first.get("title") or "").strip()

    if not md:
        return {"ok": False, "error": "pagina sem conteudo extraivel"}

    truncated = len(md) > limite
    md = md[:limite]
    if truncated:
        md += "\n\n[...] (conteudo truncado)"

    return _put(key, {
        "ok": True,
        "url": url,
        "title": title,
        "markdown": md,
        "length": len(md),
        "truncated": truncated,
        "engine": "Crawl4ai (self-hosted)",
    })


def web_research(query: str, profundidade: int = 3) -> Dict[str, Any]:
    """Pipeline completo: busca + leitura das 2-3 melhores paginas.

    Retorna um dossie pronto para a IA resumir/narrar.
    """
    busca = web_search(query, limite=profundidade + 2)
    if not busca.get("ok"):
        return busca

    paginas = []
    for r in busca["results"][:max(1, profundidade)]:
        leitura = read_url(r["url"], limite=6000)
        if leitura.get("ok"):
            paginas.append({
                "title": leitura.get("title") or r["title"],
                "url": r["url"],
                "markdown": leitura["markdown"],
            })

    return {
        "ok": True,
        "query": query,
        "results": busca["results"],
        "pages": paginas,
        "summary": busca["summary"],
        "pages_read": len(paginas),
    }


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    r = web_search("JARVIS Inteligencia Artificial", limite=3)
    print(json.dumps(r, ensure_ascii=False, indent=1)[:900])
    if r.get("ok"):
        r2 = read_url(r["results"][0]["url"], limite=800)
        print(json.dumps({k: v for k, v in r2.items() if k != "markdown"},
                         ensure_ascii=False))
        print(r2.get("markdown", "")[:400])
