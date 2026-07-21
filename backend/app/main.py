from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.api import api_router
from app.config import settings

app = FastAPI(
    title=settings.project_name,
    summary="Secure, asynchronous web ingestion for RAG pipelines",
    version="0.2.0",
    contact={"name": "Arachnin maintainers", "url": "https://github.com/M1hawk005/Arachnin"},
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    license_info={"name": "MIT", "identifier": "MIT"},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "arachnin-api"}


@app.get("/ready", tags=["operations"])
def readiness() -> dict[str, str]:
    return {"status": "ready"}
