"""
J.A.R.V.I.S. — Helper de OAuth do Spotify
Obtém o SPOTIFY_REFRESH_TOKEN da sua conta (autorização única).

USO:
  1) Crie um app em https://developer.spotify.com/dashboard
     - Adicione um Redirect URI EXATO:  http://localhost:8888/callback
  2) Rode:  python spotify_auth.py
  3) Informe Client ID e Client Secret, autorize no navegador que abrir,
     e copie o REFRESH TOKEN exibido para SPOTIFY_REFRESH_TOKEN.
"""
import base64
import http.server
import json
import socketserver
import sys
import urllib.parse
import urllib.request
import webbrowser

REDIRECT_URI = "http://localhost:8888/callback"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing user-read-email"
_auth_code = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        code = (params.get("code", [""])[0] or "").strip()
        err = (params.get("error", [""])[0] or "").strip()
        _auth_code["code"] = code
        _auth_code["error"] = err
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = "Pode fechar esta aba. Token capturado!" if code else (f"Erro: {err}" if err else "aguardando...")
        self.wfile.write(f"<h2>J.A.R.V.I.S. Spotify</h2><p>{msg}</p>".encode("utf-8"))

    def log_message(self, *a):
        pass


def main():
    print("=" * 60)
    print(" J.A.R.V.I.S. — OAuth do Spotify")
    print("=" * 60)
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    if not client_id or not client_secret:
        print("Faltou Client ID/Secret.")
        return

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    })
    print("\nAbrindo o navegador para autorizar...")
    print("Se não abrir, acesse:\n", auth_url, "\n")
    webbrowser.open(auth_url)

    with socketserver.TCPServer(("127.0.0.1", 8888), Handler) as httpd:
        httpd.timeout = 300
        for _ in range(300):
            httpd.handle_request()
            if _auth_code.get("code") or _auth_code.get("error"):
                break

    if _auth_code.get("error"):
        print("Autorização negada:", _auth_code["error"]); return
    code = _auth_code.get("code")
    if not code:
        print("Nenhum código recebido (timeout)."); return

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=data,
                                 headers={"Authorization": f"Basic {basic}",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        tok = json.loads(r.read().decode("utf-8"))

    refresh = tok.get("refresh_token")
    print("\n" + "=" * 60)
    if refresh:
        print("SUCESSO! Coloque estas variáveis no docker-compose.yml do jarvis-hud:")
        print(f"  SPOTIFY_CLIENT_ID={client_id}")
        print(f"  SPOTIFY_CLIENT_SECRET={client_secret}")
        print(f"  SPOTIFY_REFRESH_TOKEN={refresh}")
        print("  SPOTIFY_DEFAULT_DEVICE= (opcional: nome do dispositivo, ex: 'PC Werik')")
    else:
        print("Não veio refresh_token:", json.dumps(tok)[:300])
    print("=" * 60)


if __name__ == "__main__":
    main()
