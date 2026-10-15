FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn pydantic

COPY memory_server.py /app/memory_server.py
COPY jarvis_memory.py /app/jarvis_memory.py
COPY brain_dashboard.html /app/brain_dashboard.html

EXPOSE 8090

CMD ["python", "memory_server.py"]
