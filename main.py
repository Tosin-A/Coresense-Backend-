"""
CoreSense Backend Server
FastAPI application entry point.

Run with: PYTHONPATH=. python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
Or use the Procfile/Dockerfile which set PYTHONPATH automatically.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.app_api import router as app_api_router
from backend.routers.coaching_router import router as coaching_router
from backend.routers.notifications import router as notifications_router
from backend.routers.patterns import router as patterns_router
from backend.routers.subscription_router import router as subscription_router
from backend.routers.todos import router as todos_router

from backend.routers.recap_router import router as recap_router
from backend.middleware.rate_limit_middleware import RateLimitMiddleware
from backend.config import get_settings
from backend.services.scheduler_service import scheduler_service

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Starts the scheduler on startup and stops it on shutdown.
    """
    # Startup
    logger.info("Starting CoreSense Backend...")
    scheduler_service.start()
    logger.info("Background scheduler started for task reminders")

    yield

    # Shutdown
    logger.info("Shutting down CoreSense Backend...")
    scheduler_service.stop()
    logger.info("Background scheduler stopped")


# Initialize FastAPI app with lifespan
app = FastAPI(
    title="CoreSense Backend API",
    description="Backend API for CoreSense - Personal AI Coach",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS (allow app to call backend)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [
        "https://coresense-backend-production.up.railway.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Add rate limiting middleware (after CORS)
app.add_middleware(RateLimitMiddleware)

# Include routers
app.include_router(app_api_router)
app.include_router(coaching_router)
app.include_router(notifications_router)
app.include_router(patterns_router)
app.include_router(subscription_router)
app.include_router(todos_router)

app.include_router(recap_router)


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
        reload=settings.environment == "development",
        loop="asyncio"  # Explicit asyncio loop for Python 3.14 compatibility
    )
