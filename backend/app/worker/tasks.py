import socket
import requests
from requests import RequestException

from app.crud import job_crud
from app.db.session import SessionLocal
from app.models.job import JobStatus
from app.services.extraction import extract_document
from app.services.security import FetchError, fetch_public_html
from app.utils.redis_client import cache_job_status
from app.worker.celery_app import celery_app


def _stage(job_id: str, job, db, status: JobStatus) -> None:
    job_crud.set_status(db, job, status)
    cache_job_status(job_id, status.value)


@celery_app.task(bind=True, max_retries=2, name="arachnin.ingest")
def ingest_document(self, job_id: str) -> dict:
    db = SessionLocal()
    job = job_crud.get_job(db, job_id)
    if not job:
        db.close()
        return {"job_id": job_id, "status": "NOT_FOUND"}

    try:
        _stage(job_id, job, db, JobStatus.FETCHING)
        page = fetch_public_html(job.url)
        _stage(job_id, job, db, JobStatus.EXTRACTING)
        document = extract_document(page.html, job.chunk_size, job.chunk_overlap)
        _stage(job_id, job, db, JobStatus.CHUNKING)
        job_crud.complete_job(db, job, canonical_url=page.url, document=document)
        cache_job_status(job_id, JobStatus.COMPLETED.value)
        return {
            "job_id": job_id,
            "status": JobStatus.COMPLETED.value,
            "word_count": document.word_count,
            "chunk_count": len(document.chunks),
        }
    except FetchError as exc:
        job_crud.fail_job(db, job, exc.code, str(exc))
        cache_job_status(job_id, JobStatus.FAILED.value)
        return {"job_id": job_id, "status": JobStatus.FAILED.value, "error": exc.code}
    except (requests.Timeout, TimeoutError, socket.timeout) as exc:
        job_crud.fail_job(db, job, "TIMEOUT", "The request timed out.")
        cache_job_status(job_id, JobStatus.FAILED.value)
        return {"job_id": job_id, "status": JobStatus.FAILED.value, "error": "TIMEOUT"}
    except (RequestException, ConnectionError) as exc:
        if isinstance(exc, requests.Timeout):
            job_crud.fail_job(db, job, "TIMEOUT", "The request timed out.")
            cache_job_status(job_id, JobStatus.FAILED.value)
            return {"job_id": job_id, "status": JobStatus.FAILED.value, "error": "TIMEOUT"}
        if self.request.retries < self.max_retries:
            job_crud.set_status(db, job, JobStatus.QUEUED)
            cache_job_status(job_id, JobStatus.QUEUED.value)
            raise self.retry(exc=exc, countdown=2 ** (self.request.retries + 1)) from exc
        job_crud.fail_job(db, job, "FETCH_FAILED", "The destination remained unavailable.")
        return {"job_id": job_id, "status": JobStatus.FAILED.value}
    except ValueError as exc:
        job_crud.fail_job(db, job, "EXTRACTION_FAILED", str(exc))
        cache_job_status(job_id, JobStatus.FAILED.value)
        return {"job_id": job_id, "status": JobStatus.FAILED.value}
    except Exception:
        job_crud.fail_job(db, job, "INTERNAL_ERROR", "The ingestion pipeline failed unexpectedly.")
        cache_job_status(job_id, JobStatus.FAILED.value)
        raise
    finally:
        db.close()
