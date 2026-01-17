# Dockerfile for CoreSense Backend
# This Dockerfile is designed to be built from the backend/ directory
# Build command: cd backend && docker build -t coresense-backend .

FROM python:3.12-slim

# Set environment variables
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
# Increase pip timeout and use --default-timeout for large packages
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=100 -r /tmp/requirements.txt

# Copy all backend code to /app/backend/ to preserve import structure
# main.py expects to be in /app/backend/ and imports from backend.config
# It adds parent (/app) to sys.path, allowing 'backend.config' to resolve
COPY . /app/backend/

# Create non-root user for security and set permissions
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app && \
    chmod +x /app/backend/start.sh

# Switch to non-root user
USER app

# Set working directory to where main.py is located
WORKDIR /app/backend

# Expose port (default to 8000, Railway will set PORT env var at runtime)
EXPOSE 8000

# Health check (uses default 8000, Railway's PORT env will override in CMD)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use ENTRYPOINT with startup script for proper variable expansion
# Use exec form but explicitly call sh to execute the script
ENTRYPOINT ["sh", "/app/backend/start.sh"]
