#!/bin/sh
set -e

# Change to backend directory
cd /app/backend || exit 1

# Get PORT from Railway environment variable, default to 8000
PORT="${PORT:-8000}"

# Start uvicorn server
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}" --workers 1
