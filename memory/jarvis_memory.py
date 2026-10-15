"""
J.A.R.V.I.S. Centralized Agentic Memory Python SDK Client
Permite que o server.py, o OpenClaw, o Antigravity e qualquer agente leiam e gravem memórias no Cérebro Central.
"""

import urllib.request
import json
import time

DEFAULT_URLS = [
    "${ZIMA_ROUTER_URL:-http://127.0.0.1:8095}",
    "http://127.0.0.1:8090"
]

class JarvisMemoryClient:
    def __init__(self, base_urls=None):
        if base_urls is None:
            self.base_urls = DEFAULT_URLS
        elif isinstance(base_urls, str):
            self.base_urls = [base_urls]
        else:
            self.base_urls = base_urls

    def _request(self, endpoint: str, data=None, headers=None, method="GET"):
        if headers is None:
            headers = {}
        for base_url in self.base_urls:
            try:
                url = f"{base_url}{endpoint}"
                req_headers = {"User-Agent": "JarvisMemoryClient/1.0", **headers}
                req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception:
                continue
        return None

    def remember(self, title: str, content: str, project: str = "JARVIS", mem_type: str = "conversation", tags: str = "", importance: int = 3):
        """Grava um nó de conhecimento ou contexto na Memória Central (ZimaOS ou Local)."""
        payload = json.dumps({
            "project": project,
            "type": mem_type,
            "title": title,
            "content": content,
            "tags": tags,
            "importance": importance
        }).encode("utf-8")
        res = self._request("/api/memory/remember", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        return res if res else {"status": "error", "message": "Nenhum servidor de memória disponível."}

    def recall(self, query: str, project: str = None):
        """Recupera memórias relevantes por busca semântica/palavra-chave."""
        endpoint = f"/api/memory/recall?query={urllib.parse.quote(query)}"
        if project:
            endpoint += f"&project={urllib.parse.quote(project)}"
        res = self._request(endpoint, method="GET")
        return res if res else {"query": query, "total_found": 0, "memories": []}

    def get_graph(self):
        """Retorna o grafo 3D completo de nós e links."""
        res = self._request("/api/memory/graph", method="GET")
        return res if res else {"nodes": [], "links": []}

# Instance singleton
memory_client = JarvisMemoryClient()
