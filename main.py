"""
CoreSense Backend Server
FastAPI application entry point.

Run with: PYTHONPATH=. python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
Or use the Procfile/Dockerfile which set PYTHONPATH automatically.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.app_api import router as app_api_router
from backend.routers.coaching_router import router as coaching_router
from backend.routers.notifications import router as notifications_router
from backend.routers.patterns import router as patterns_router
# from backend.routers.wellness_router import router as wellness_router  # TODO: Enable after creating wellness services
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
# app.include_router(wellness_router)  # TODO: Enable after creating wellness services


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
    import os
    import uvicorn
    settings = get_settings()
    port = int(os.environ.get("PORT", settings.port))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.environment == "development"
    )
