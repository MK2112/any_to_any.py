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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpango-1.0-0 \
    libcairo2 \
    libpango1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

# Directories for uploads and conversions
RUN mkdir -p uploads converted
# Expose port for web interface
EXPOSE 5000
# Set environment variables
ENV FLASK_APP=web_to_any.py
ENV PYTHONUNBUFFERED=1
# Default: start web interface
CMD ["python", "any_to_any.py", "-w"]
