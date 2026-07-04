# ========================================
# XM Global MT5 — Python AI Service
# ========================================
# Build:  docker build -t xm-mt5-ai .
# Run:    docker run -p 8000:8000 -p 8080:8080 -v ./logs:/app/logs -v ./data:/app/data xm-mt5-ai
# ========================================

FROM python:3.13-slim

LABEL org.opencontainers.image.title="XM Global MT5 AI Service"
LABEL org.opencontainers.image.description="DeepSeek-powered trading analysis service"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements.lock ./

RUN pip install --no-cache-dir -r requirements.lock

COPY core/ ./core/
COPY src/ ./src/
COPY configs/ ./configs/
COPY config.py .
COPY check_config.py .
COPY check_core_components.py .

RUN mkdir -p /app/logs /app/data /app/MQL5/Files

EXPOSE 8000 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import os; exit(0 if os.path.exists('/app/MQL5/Files/service_ready.json') else 1)" || exit 1

CMD ["python", "mt5_ai_service.py", "--mode", "file"]
