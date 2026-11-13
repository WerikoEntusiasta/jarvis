"""
J.A.R.V.I.S. — APIs Públicas (sem chave, sem cadastro)
=============================================================================
- Previsão do tempo : Open-Meteo (geocoding + forecast, 7 dias)
- Notícias           : Google News RSS (pt-BR, qualquer tema)

Ambas validadas em produção: sem API key, sem rate limit agressivo.
Usado pelas tools do Qwen e pelos cards dinâmicos do HUD.
"""

import re
import time
import html as html_lib
import logging
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("PublicAPIs")

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_NEWS_URL = "https://news.google.com/rss/search"

_CACHE: Dict[str, Tuple[float, Any]] = {}
_CACHE_TTL = 600.0  # 10 minutos


def _cached_get(key: str):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _cache_put(key: str, value):
    _CACHE[key] = (time.time(), value)
    return value


def _http_get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# --------------------------------------------------------------------------- #
# Previsao do tempo (Open-Meteo)
# --------------------------------------------------------------------------- #

# Codigos WMO -> descricao pt-BR + emoji
_WMO_PT: Dict[int, Tuple[str, str]] = {
    0: ("Céu limpo", "☀️"),
    1: ("Predominantemente limpo", "🌤️"),
    2: ("Parcialmente nublado", "⛅"),
    3: ("Encoberto", "☁️"),
    45: ("Névoa", "🌫️"),
    48: ("Névoa com geada", "🌫️"),
    51: ("Garoa fraca", "🌦️"),
    53: ("Garoa moderada", "🌦️"),
    55: ("Garoa intensa", "🌦️"),
    56: ("Garoa congelante", "🌧️"),
    57: ("Garoa congelante forte", "🌧️"),
    61: ("Chuva fraca", "🌧️"),
    63: ("Chuva moderada", "🌧️"),
    65: ("Chuva forte", "🌧️"),
    66: ("Chuva congelante", "🧊"),
    67: ("Chuva congelante forte", "🧊"),
    71: ("Neve fraca", "🌨️"),
    73: ("Neve moderada", "🌨️"),
    75: ("Neve forte", "❄️"),
    77: ("Grãos de neve", "❄️"),
    80: ("Pancadas isoladas", "🌦️"),
    81: ("Pancadas de chuva", "🌧️"),
    82: ("Pancadas fortes", "⛈️"),
    85: ("Pancadas de neve", "🌨️"),
    86: ("Pancadas de neve fortes", "❄️"),
    95: ("Tempestade elétrica", "⛈️"),
    96: ("Tempestade com granizo", "⛈️"),
    99: ("Tempestade forte com granizo", "🌩️"),
}

_DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def geocode(cidade: str) -> Optional[Dict[str, Any]]:
    """Busca coordenadas de uma cidade via Open-Meteo Geocoding (pt)."""
    if not cidade or not str(cidade).strip():
        return None
    key = "geo:" + str(cidade).strip().lower()
    hit = _cached_get(key)
    if hit is not None:
        return hit
    qs = urllib.parse.urlencode({
        "name": str(cidade).strip(),
        "count": 1,
        "language": "pt",
        "format": "json",
    })
    try:
        import json
        data = json.loads(_http_get(f"{_GEO_URL}?{qs}"))
        results = data.get("results") or []
        if not results:
            return None
        r = results[0]
        geo = {
            "nome": r.get("name", cidade),
            "regiao": r.get("admin1", ""),
            "pais": r.get("country", ""),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "timezone": r.get("timezone", "auto"),
        }
        return _cache_put(key, geo)
    except Exception as e:
        logger.warning(f"[PublicAPIs] geocoding falhou para '{cidade}': {e}")
        return None


def fetch_weather(cidade: str, dias: int = 7) -> Optional[Dict[str, Any]]:
    """Previsao diaria de 7 dias (max/min, tempo, chuva, vento).

    Retorna dict com city + days[] prontos para o weather_card.
    """
    if not cidade or not str(cidade).strip():
        return None
    dias = max(1, min(16, int(dias or 7)))
    key = f"wx:{str(cidade).strip().lower()}:{dias}"
    hit = _cached_get(key)
    if hit is not None:
        return hit

    geo = geocode(cidade)
    if not geo:
        return None

    import json
    qs = urllib.parse.urlencode({
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "daily": ",".join([
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_probability_max",
            "precipitation_sum",
            "wind_speed_10m_max",
        ]),
        "timezone": geo.get("timezone") or "auto",
        "forecast_days": dias,
    })
    try:
        data = json.loads(_http_get(f"{_FORECAST_URL}?{qs}"))
    except Exception as e:
        logger.warning(f"[PublicAPIs] forecast falhou para '{cidade}': {e}")
        return None

    daily = data.get("daily") or {}
    times = daily.get("time") or []
    days: List[Dict[str, Any]] = []
    for i, iso in enumerate(times):
        try:
            wmo = int((daily.get("weather_code") or [0])[i])
        except (ValueError, TypeError, IndexError):
            wmo = 0
        desc, emoji = _WMO_PT.get(wmo, ("Tempo indefinido", "🌡️"))
        dow = ""
        try:
            dow = _DIAS_SEMANA[time.strptime(iso, "%Y-%m-%d").tm_wday]
        except Exception:
            pass
        days.append({
            "date": iso,
            "weekday": dow,
            "description": desc,
            "emoji": emoji,
            "weather_code": wmo,
            "temp_max": (daily.get("temperature_2m_max") or [None])[i],
            "temp_min": (daily.get("temperature_2m_min") or [None])[i],
            "rain_prob": (daily.get("precipitation_probability_max") or [None])[i],
            "rain_sum": (daily.get("precipitation_sum") or [None])[i],
            "wind_max": (daily.get("wind_speed_10m_max") or [None])[i],
        })

    if not days:
        return None

    primeiro = days[0]
    resumo = (
        f"{geo['nome']}: hoje {primeiro['description'].lower()} "
        f"com máxima de {primeiro['temp_max']}°C e mínima de {primeiro['temp_min']}°C, "
        f"{primeiro['rain_prob']}% de chance de chuva."
    )
    payload = {
        "city": geo["nome"],
        "region": geo.get("regiao") or "",
        "country": geo.get("pais") or "",
        "timezone": data.get("timezone") or geo.get("timezone") or "auto",
        "days": days,
        "summary": resumo,
        "source": "Open-Meteo",
        "fetched_at": time.time(),
    }
    return _cache_put(key, payload)


# --------------------------------------------------------------------------- #
# Noticias (Google News RSS pt-BR)
# --------------------------------------------------------------------------- #

_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return html_lib.unescape(_TAG_RE.sub(" ", text)).strip()


def fetch_news(tema: str = "brasil", limite: int = 6,
               quando: str = "") -> Optional[Dict[str, Any]]:
    """Noticias do Google News (RSS pt-BR) para um tema/livre.

    Returns dict com topic, items[{title, link, source, published, summary,
    image}] e summary textual para a narração.
    """
    tema = str(tema or "brasil").strip() or "brasil"
    limite = max(1, min(12, int(limite or 6)))
    key = f"news:{tema.lower()}:{limite}:{str(quando).strip().lower()}"
    hit = _cached_get(key)
    if hit is not None:
        return hit

    query = tema + (f" {quando}" if quando else "")
    qs = urllib.parse.urlencode({
        "q": query,
        "hl": "pt-BR",
        "gl": "BR",
        "ceid": "BR:pt-419",
    })
    try:
        raw = _http_get(f"{_NEWS_URL}?{qs}")
        root = ET.fromstring(raw)
    except Exception as e:
        logger.warning(f"[PublicAPIs] news RSS falhou para '{tema}': {e}")
        return None

    ns = {"media": "http://search.yahoo.com/mrss/"}
    items: List[Dict[str, Any]] = []
    for node in root.iter("item"):
        if len(items) >= limite:
            break
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not title:
            continue
        source = (node.findtext("source") or "").strip()
        if not source and " - " in title:
            title, _, source = title.rpartition(" - ")
        published = (node.findtext("pubDate") or "").strip()
        desc = _strip_html(node.findtext("description") or "")

        image = ""
        media = node.find("media:content", ns)
        if media is not None and media.get("url"):
            image = media.get("url", "")
        if not image:
            media = node.find("media:thumbnail", ns)
            if media is not None and media.get("url"):
                image = media.get("url", "")
        if not image:
            m = _IMG_RE.search(node.findtext("description") or "")
            if m:
                image = m.group(1)

        items.append({
            "title": title,
            "link": link,
            "source": source or "Google Notícias",
            "published": published,
            "summary": desc[:400],
            "image": image,
        })

    if not items:
        return None

    topico = tema if len(tema) < 40 else tema[:37] + "..."
    resumo = f"Manchetes sobre {topico}: " + "; ".join(
        i["title"].lower().rstrip(".") for i in items[:3]
    ) + "."
    payload = {
        "topic": topico,
        "items": items,
        "summary": resumo,
        "source": "Google Notícias",
        "fetched_at": time.time(),
    }
    return _cache_put(key, payload)


# --------------------------------------------------------------------------- #
# Tool-facing: dispatch rapido
# --------------------------------------------------------------------------- #

def get_public_data(kind: str, **kwargs) -> Dict[str, Any]:
    """Dispatch unico para as tools do modelo de conversacao."""
    kind = str(kind or "").strip().lower()
    try:
        if kind in ("weather", "tempo", "clima", "previsao"):
            dados = fetch_weather(
                str(kwargs.get("cidade") or kwargs.get("city") or ""),
                int(kwargs.get("dias") or 7),
            )
        elif kind in ("news", "noticia", "noticias"):
            dados = fetch_news(
                str(kwargs.get("tema") or "brasil"),
                int(kwargs.get("limite") or 6),
                str(kwargs.get("quando") or ""),
            )
        else:
            return {"ok": False, "error": f"tipo desconhecido: {kind}"}
    except Exception as e:
        logger.exception(f"[PublicAPIs] get_public_data({kind}) falhou")
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    if not dados:
        return {"ok": False, "error": f"nenhum dado de {kind} encontrado"}
    return {"ok": True, "kind": kind, "data": dados}


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(get_public_data("weather", cidade="São Paulo"),
                      ensure_ascii=False, indent=2)[:1200])
    print(_json.dumps(get_public_data("news", tema="tecnologia", limite=3),
                      ensure_ascii=False, indent=2)[:1200])
