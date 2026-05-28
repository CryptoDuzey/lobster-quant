FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /build/front
COPY front/package*.json ./
RUN npm ci
COPY front/ ./
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    LOBSTER_DB_PATH=/mnt/workspace/lobster_quant.db \
    LOBSTER_CACHE_DIR=/mnt/workspace/cache \
    LOBSTER_FRONTEND_DIST=/home/user/app/front/dist

WORKDIR /home/user/app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY app.py app.py
COPY --from=frontend-builder /build/front/dist front/dist

EXPOSE 7860

ENTRYPOINT ["python", "-u", "app.py"]
