# --- build the UI
FROM node:22-alpine AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build --outDir /app/static --emptyOutDir

# --- runtime
FROM python:3.12-slim
WORKDIR /app
COPY backend/ ./backend/
COPY --from=ui /app/static ./backend/kelvo/static
RUN pip install --no-cache-dir ./backend \
 && useradd --system --uid 10001 --home-dir /data kelvo \
 && mkdir -p /data && chown kelvo:kelvo /data
USER kelvo
ENV KELVO_DB=/data/kelvo.db \
    OLLAMA_BASE_URL=http://ollama:11434 \
    PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=3)"
CMD ["kelvo", "run", "--host", "0.0.0.0", "--port", "7860"]
