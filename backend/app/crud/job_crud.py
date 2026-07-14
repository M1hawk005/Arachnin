from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus


def create_job(db: Session, *, url: str, chunk_size: int, chunk_overlap: int) -> Job:
    job = Job(url=url, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Job | None:
    return db.get(Job, job_id)


def list_jobs(db: Session, limit: int = 20) -> list[Job]:
    statement = select(Job).order_by(Job.created_at.desc()).limit(limit)
    return list(db.scalars(statement))


def set_status(db: Session, job: Job, status: JobStatus) -> Job:
    job.status = status
    db.commit()
    db.refresh(job)
    return job


def complete_job(db: Session, job: Job, *, canonical_url: str, document) -> Job:
    job.url = canonical_url
    job.status = JobStatus.COMPLETED
    job.title = document.title
    job.description = document.description
    job.site_name = document.site_name
    job.author = document.author
    job.published_at = document.published_at
    job.language = document.language
    job.content = document.content
    job.content_hash = document.content_hash
    job.word_count = document.word_count
    job.chunks = document.chunks
    job.error_code = None
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


def fail_job(db: Session, job: Job, code: str, message: str) -> Job:
    job.status = JobStatus.FAILED
    job.error_code = code
    job.error_message = message
    db.commit()
    db.refresh(job)
    return job
