# PORT Variable Fix - Summary

## Problem
Railway was passing `$PORT` as a literal string instead of expanding it, causing:
```
Error: Invalid value for '--port': '$PORT' is not a valid integer.
```

## Solution Applied

1. **Removed `startCommand` from `railway.json`**
   - Railway will now use the Dockerfile ENTRYPOINT/CMD
   - This ensures consistent behavior

2. **Updated Dockerfile to use ENTRYPOINT**
   - Uses `/app/backend/start.sh` as ENTRYPOINT
   - This script runs in a shell, allowing proper variable expansion

3. **Simplified startup script (`start.sh`)**
   - Properly expands `${PORT:-8000}` at runtime
   - Uses `exec` to replace shell with uvicorn process
   - Handles directory change correctly

## Files Changed

### `railway.json`
- Removed `startCommand` (now uses Dockerfile ENTRYPOINT)

### `Dockerfile`
- Added `ENTRYPOINT ["/app/backend/start.sh"]`
- Script is made executable during build

### `start.sh`
- Simple shell script that expands PORT variable
- Changes to `/app/backend` directory
- Executes uvicorn with proper port

## How It Works

1. Railway sets `PORT` environment variable (e.g., `PORT=8080`)
2. Docker container starts and executes `start.sh` (ENTRYPOINT)
3. Script reads `${PORT:-8000}` which expands to Railway's PORT or defaults to 8000
4. Script runs: `uvicorn main:app --host 0.0.0.0 --port 8080 --workers 1`
5. Server starts successfully

## Testing

After deployment, verify:
```bash
railway domain  # Get your URL
curl https://your-url.railway.app/health
```

Should return: `{"status":"healthy","service":"coresense-backend"}`

## If Issues Persist

1. **Clear Railway cache/deploy fresh:**
   ```bash
   railway up --detach
   ```

2. **Check Railway logs:**
   ```bash
   railway logs
   ```

3. **Verify PORT is set in Railway:**
   - Railway automatically sets PORT, but verify in dashboard
   - Go to Variables tab and ensure PORT exists (Railway sets this automatically)

4. **Manual override (if needed):**
   - In Railway dashboard → Variables → Add `PORT=8000`
   - Or use: `railway variables set PORT=8000`
