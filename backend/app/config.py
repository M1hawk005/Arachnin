"""Environment-backed settings for the Arachnin ingestion service."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    project_name: str = os.getenv("PROJECT_NAME", "Arachnin")
    environment: str = os.getenv("ENVIRONMENT", "development")
    database_url: str = os.getenv(
        "DATABASE_URL", os.getenv("POSTGRES_URI", "sqlite:///./arachnin.db")
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    broker_url: str = os.getenv(
        "BROKER_URL", os.getenv("RABBITMQ_URI", "amqp://guest:guest@rabbitmq:5672//")
    )
    result_backend_url: str = os.getenv("RESULT_BACKEND_URL", "redis://redis:6379/1")
    cors_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if value.strip()
    )
    fetch_timeout_seconds: float = float(os.getenv("FETCH_TIMEOUT_SECONDS", "15"))
    max_document_bytes: int = int(os.getenv("MAX_DOCUMENT_BYTES", "5000000"))
    max_redirects: int = int(os.getenv("MAX_REDIRECTS", "3"))


settings = Settings()
