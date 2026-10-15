FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir aiohttp numpy onnxruntime openwakeword
RUN python -c "import openwakeword; openwakeword.utils.download_models()"
COPY jarvis_screen_router.py /app/
EXPOSE 8095
CMD ["python", "-u", "jarvis_screen_router.py"]
