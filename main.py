"""
CoreSense Backend Server
FastAPI application entry point.
"""

import sys
from pathlib import Path

# Add parent directory to Python path for absolute imports
# This allows imports like 'from backend.config import ...'
backend_dir = Path(__file__).parent
parent_dir = backend_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.app_api import router as app_api_router
from backend.routers.coaching_router import router as coaching_router
from backend.routers.notifications import router as notifications_router
from backend.routers.patterns import router as patterns_router
from backend.middleware.rate_limit_middleware import RateLimitMiddleware
from backend.config import get_settings

# Initialize FastAPI app
app = FastAPI(
    title="CoreSense Backend API",
    description="Backend API for CoreSense - Personal AI Coach",
    version="1.0.0"
)

# Configure CORS (allow app to call backend)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware (after CORS)
#TEMPORARILY DISABLED - Uncomment after running DATABASE_SETUP_GUIDE.md
# app.add_middleware(RateLimitMiddleware)

# Include routers
app.include_router(app_api_router)
app.include_router(coaching_router)
app.include_router(notifications_router)
app.include_router(patterns_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "coresense-backend"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "CoreSense Backend API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.environment == "development"
    )
