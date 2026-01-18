# Dockerfile for CoreSense Backend
# This Dockerfile is designed to be built from the backend/ directory
# Build command: cd backend && docker build -t coresense-backend .

FROM python:3.12-slim

# Set environment variables
# PYTHONPATH=/app allows imports like 'from backend.config import ...'
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
# Use production requirements (excludes heavy ML packages)
COPY requirements-prod.txt /tmp/requirements.txt

# Install Python dependencies (as root, before creating user)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r /tmp/requirements.txt

# Copy all backend code to /app/backend/ to preserve import structure
COPY . /app/backend/

# Create non-root user for security and set permissions
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app && \
    chmod +x /app/backend/start.sh

# Switch to non-root user
USER app

# Expose port (default to 8000, Railway will set PORT env var at runtime)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use startup script which handles PORT env var
ENTRYPOINT ["sh", "/app/backend/start.sh"]
