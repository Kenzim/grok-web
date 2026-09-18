FROM node:22-bookworm-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
ARG GROKBOT_CLIENT_GIT=https://git.stackken.com/kenzim/grokbot-client.git
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY --from=frontend /src/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e . \
    && pip install --no-cache-dir "git+${GROKBOT_CLIENT_GIT}"
ENV PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8787"]
