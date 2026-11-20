FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py main.py jobstore.py worker.py cleanup.py ./
COPY services/ ./services/
COPY utils/ ./utils/

RUN mkdir -p /app/downloads

EXPOSE 8200

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8200}"]
