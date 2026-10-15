FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Silero VAD streaming model, pinned to the official v6.2.3 release.
RUN mkdir -p /opt/jarvis/models \
    && curl --fail --location --retry 4 \
       https://raw.githubusercontent.com/snakers4/silero-vad/5cd7945/src/silero_vad/data/silero_vad.onnx \
       --output /opt/jarvis/models/silero_vad.onnx \
    && test "$(stat -c %s /opt/jarvis/models/silero_vad.onnx)" -gt 2000000

# Preload the official hey_jarvis model so wake detection does not depend on
# an internet download during the first sphere connection.
RUN mkdir -p /opt/jarvis/models/wakeword \
    && python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis_v0.1'], target_directory='/opt/jarvis/models/wakeword')" \
    && test -s /opt/jarvis/models/wakeword/hey_jarvis_v0.1.onnx

COPY . .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080 8081 8082 8095 8096

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/api/hud/diag || exit 1

# Sobe o servidor MCP (porta 8081) em background e o Core Server em primeiro plano
CMD ["sh", "-c", "python mcp_hud_server.py & exec python server.py"]
