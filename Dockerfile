# syntax=docker/dockerfile:1

# Stage 1: build the React frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# The API is served from the same origin as the frontend
ENV VITE_API_BASE_URL=/api
RUN npm run build

# Stage 2: Django API, which also serves the built frontend (WhiteNoise)
FROM python:3.12-slim AS runner
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DJANGO_DEBUG=false \
    FRONTEND_DIST_DIR=/app/frontend_dist
# DJANGO_SECRET_KEY must be supplied at runtime (render.yaml generates one on Render)

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-builder /app/frontend/dist /app/frontend_dist

WORKDIR /app/backend
EXPOSE 8000

# One worker process with threads: route, weather and place caches live in process memory,
# so a single process lets every request share them. Binds to the platform's $PORT.
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 180"]
