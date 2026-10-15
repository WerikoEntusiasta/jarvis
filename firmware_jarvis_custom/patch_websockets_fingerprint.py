from pathlib import Path


Import("env")

source_path = (
    Path(env.subst("$PROJECT_LIBDEPS_DIR"))
    / env.subst("$PIOENV")
    / "WebSockets"
    / "src"
    / "WebSocketsClient.cpp"
)
source = source_path.read_text(encoding="utf-8")
before = "} else if(!SSL_FINGERPRINT_IS_SET) {\n                _client.ssl->setInsecure();"
after = "} else {\n                _client.ssl->setInsecure();"

if before in source:
    source_path.write_text(source.replace(before, after, 1), encoding="utf-8")
elif after not in source:
    raise RuntimeError("WebSockets TLS fingerprint hook no longer matches expected source")
