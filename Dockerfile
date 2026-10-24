# syntax=docker/dockerfile:1

# Stage 1: Build Frontend Assets
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Django Backend & Static Serving
FROM python:3.12-slim AS runner
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
# Production defaults; supply DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS and CORS_ALLOWED_ORIGINS at runtime
ENV DJANGO_DEBUG=false

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt gunicorn whitenoise

# Copy Backend Source
COPY backend/ ./backend/

# Copy Frontend Build Output into Django Staticfiles / Template directory
COPY --from=frontend-builder /app/frontend/dist /app/frontend_dist

WORKDIR /app/backend


EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
