from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.crud import job_crud
from app.models.job import Job, JobStatus
from app.schemas.extract import (
    DocumentMetadata,
    IngestionResult,
    IngestRequest,
    JobAccepted,
    JobStatusResponse,
    JobSummary,
)
from app.ingestion.validators import validate_public_url
from app.services.security import FetchError
from app.utils.redis_client import cache_job_status, get_cached_status
from app.worker.tasks import ingest_document

router = APIRouter(prefix="/ingestions", tags=["ingestions"])

STAGE_PROGRESS = {
    JobStatus.QUEUED: ("Queued", 10),
    JobStatus.FETCHING: ("Fetching document", 30),
    JobStatus.EXTRACTING: ("Extracting content", 55),
    JobStatus.CHUNKING: ("Preparing chunks", 80),
    JobStatus.COMPLETED: ("Ready", 100),
    JobStatus.FAILED: ("Failed", 100),
}


def _job_or_404(db: Session, job_id: str) -> Job:
    job = job_crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion not found")
    return job


@router.post("", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def create_ingestion(payload: IngestRequest, db: Session = Depends(get_db)) -> JobAccepted:
    url = str(payload.url)
    try:
        validate_public_url(url)
    except FetchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    job = job_crud.create_job(
        db, url=url, chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap
    )
    cache_job_status(job.id, job.status.value)
    try:
        ingest_document.delay(job.id)
    except Exception as exc:
        job_crud.fail_job(db, job, "QUEUE_UNAVAILABLE", "The ingestion queue is unavailable.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "QUEUE_UNAVAILABLE", "message": "The ingestion queue is unavailable."},
        ) from exc
    return JobAccepted(
        job_id=job.id,
        status=job.status,
        status_url=f"/api/v1/ingestions/{job.id}",
    )


@router.get("", response_model=list[JobSummary])
def recent_ingestions(
    limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)
) -> list[JobSummary]:
    return [
        JobSummary.model_validate(
            {
                "id": job.id,
                "url": job.url,
                "status": job.status,
                "title": job.title,
                "word_count": job.word_count,
                "chunk_count": len(job.chunks or []),
                "created_at": job.created_at,
            }
        )
        for job in job_crud.list_jobs(db, limit)
    ]


@router.get("/{job_id}", response_model=JobStatusResponse)
def ingestion_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = _job_or_404(db, job_id)
    cached = get_cached_status(job_id)
    current_status = JobStatus(cached) if cached else job.status
    stage, progress = STAGE_PROGRESS[current_status]
    error = None
    if job.error_code:
        error = {"code": job.error_code, "message": job.error_message or "Ingestion failed."}
    return JobStatusResponse(
        job_id=job.id,
        status=current_status,
        stage=stage,
        progress=progress,
        error=error,
    )


@router.get("/{job_id}/result", response_model=IngestionResult)
def ingestion_result(job_id: str, db: Session = Depends(get_db)) -> IngestionResult:
    job = _job_or_404(db, job_id)
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ingestion is not complete"
        )
    return IngestionResult(
        job_id=job.id,
        status=job.status,
        metadata=DocumentMetadata(
            title=job.title,
            description=job.description,
            site_name=job.site_name,
            author=job.author,
            published_at=job.published_at,
            language=job.language,
            canonical_url=job.url,
            content_hash=job.content_hash or "",
            word_count=job.word_count or 0,
        ),
        content=job.content or "",
        chunks=job.chunks or [],
    )
