#!/bin/sh
set -e

# Stay in /app where PYTHONPATH is set
cd /app || exit 1

# Get PORT from Railway environment variable, default to 8000
PORT="${PORT:-8000}"

# Start uvicorn server using fully qualified module path
# PYTHONPATH=/app allows 'backend.main' to resolve
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}" --workers 1
