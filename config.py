"""
Configuration management for CoreSense backend.
Loads and validates environment variables.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Supabase
    supabase_url: str
    supabase_service_key: str
    
    # Server
    port: int = 8000
    environment: str = "development"
    
    # Optional: Will be needed in later milestones
    openai_api_key: Optional[str] = None
    gpt_model: Optional[str] = "gpt-4o-mini"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields in .env
    )


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get global settings instance, creating it if necessary."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
