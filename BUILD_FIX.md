# Railway Build Fix - Production Requirements

## Problem

The build was failing because `requirements.txt` includes heavy ML packages:
- `torch` (~2GB)
- `transformers` (~500MB)
- `mlx-metal` (macOS-only, won't work on Linux Railway servers)

These packages:
1. Take too long to download/install
2. Cause memory issues during build
3. Aren't needed for the API server

## Solution

Created `requirements-prod.txt` with only the packages needed for the FastAPI backend API:
- FastAPI, Uvicorn (web server)
- Supabase client (database)
- OpenAI client (AI chat)
- Essential utilities

**Excluded**: ML training packages (torch, transformers, mlx, etc.)

## Next Steps

1. **The Dockerfile now uses `requirements-prod.txt` automatically**

2. **To use full requirements locally (for ML features):**
   ```bash
   pip install -r requirements.txt  # Full dev setup
   ```

3. **For production deployment:**
   ```bash
   # Dockerfile automatically uses requirements-prod.txt
   railway up
   ```

## If You Need ML Features in Production

If you actually need ML features in the production API:
1. Use a separate ML service/server
2. Or use Railway's larger instance types
3. Or pre-build a Docker image with ML packages and push to a registry

For now, the API server works fine without ML packages - they were likely only needed for training/development.
