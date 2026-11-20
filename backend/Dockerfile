# Build context is the REPO ROOT (not backend/), so this image can include
# both backend/ and frontend/ — main.py mounts ../frontend relative to itself
# to serve the static UI from the same process/port as the API.
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/config.py backend/main.py backend/jobstore.py backend/worker.py backend/cleanup.py ./backend/
COPY backend/services/ ./backend/services/
COPY backend/utils/ ./backend/utils/
COPY frontend/ ./frontend/

RUN mkdir -p /app/backend/downloads

WORKDIR /app/backend

EXPOSE 8200

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8200}"]
