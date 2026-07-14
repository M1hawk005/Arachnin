from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.deps import get_db
from app.crud import job_crud
from app.models.job import JobStatus
from app.schemas.extract import IngestRequest


def test_job_updates_and_ordering(db):
    first = job_crud.create_job(db, url="https://example.com/one", chunk_size=300, chunk_overlap=30)
    second = job_crud.create_job(
        db, url="https://example.com/two", chunk_size=500, chunk_overlap=50
    )

    job_crud.set_status(db, first, JobStatus.FETCHING)
    assert first.status == JobStatus.FETCHING
    assert job_crud.list_jobs(db, limit=1) == [second]

    document = SimpleNamespace(
        title="Stored",
        description=None,
        site_name=None,
        author=None,
        published_at=None,
        language="en",
        content="stored content",
        content_hash="c" * 64,
        word_count=2,
        chunks=[{"index": 0, "text": "stored content", "word_count": 2}],
    )
    job_crud.complete_job(db, first, canonical_url="https://example.com/final", document=document)
    assert first.status == JobStatus.COMPLETED
    assert first.content_hash == "c" * 64

    job_crud.fail_job(db, second, "TEST_FAILURE", "Expected failure")
    assert second.status == JobStatus.FAILED
    assert second.error_message == "Expected failure"


def test_ingest_request_rejects_invalid_overlap():
    with pytest.raises(ValidationError, match="smaller than chunk_size"):
        IngestRequest(url="https://example.com", chunk_size=200, chunk_overlap=200)


def test_database_dependency_closes_session(monkeypatch):
    closed = []
    fake = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr("app.api.deps.SessionLocal", lambda: fake)
    dependency = get_db()
    assert next(dependency) is fake
    dependency.close()
    assert closed == [True]
