# --- build the UI
FROM node:22-alpine AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build --outDir /app/static

# --- runtime
FROM python:3.12-slim
WORKDIR /app
COPY backend/ ./backend/
COPY --from=ui /app/static ./backend/mbdaflow/static
RUN pip install --no-cache-dir ./backend
ENV MBDAFLOW_DB=/data/mbdaflow.db \
    OLLAMA_BASE_URL=http://ollama:11434
VOLUME /data
EXPOSE 7860
CMD ["mbdaflow", "run", "--host", "0.0.0.0", "--port", "7860"]
