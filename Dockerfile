# Dockerfile for any_to_any.py
FROM python:3.11-slim as builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpango1.0-dev \
    libcairo2-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements_web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements_web.txt


FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libgdk-pixbuf-2.0-0 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

RUN useradd --create-home --shell /usr/sbin/nologin --uid 1000 appuser \
    && mkdir -p uploads converted out \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

ENV FLASK_APP=web_to_any.py \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    Any2Any_HOST=0.0.0.0 \
    Any2Any_PORT=5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('Any2Any_PORT', '5000') + '/', timeout=3)"

CMD gunicorn --bind ${Any2Any_HOST}:${Any2Any_PORT} \
    --workers 1 \
    --threads 8 \
    --timeout 300 \
    --graceful-timeout 30 \
    web_to_any:app
