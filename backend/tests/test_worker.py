from types import SimpleNamespace

from app.crud import job_crud
from app.models.job import JobStatus
from app.services.security import FetchedPage, FetchError
from app.worker.tasks import ingest_document


def make_document():
    content = "reliable retrieval content " * 20
    return SimpleNamespace(
        title="Worker result",
        description="Processed asynchronously",
        site_name="Example",
        author="Engineer",
        published_at="2026-07-14",
        language="en",
        content=content,
        content_hash="b" * 64,
        word_count=len(content.split()),
        chunks=[{"index": 0, "text": content, "word_count": len(content.split())}],
    )


def test_worker_completes_job(db, monkeypatch):
    job = job_crud.create_job(
        db, url="https://example.com/article", chunk_size=500, chunk_overlap=50
    )
    statuses = []
    monkeypatch.setattr(
        "app.worker.tasks.fetch_public_html",
        lambda _: FetchedPage("https://example.com/final", "<html></html>", "text/html"),
    )
    monkeypatch.setattr("app.worker.tasks.extract_document", lambda *args: make_document())
    monkeypatch.setattr(
        "app.worker.tasks.cache_job_status", lambda job_id, status: statuses.append(status)
    )

    outcome = ingest_document.run(job.id)

    db.expire_all()
    completed = job_crud.get_job(db, job.id)
    assert outcome["status"] == "COMPLETED"
    assert completed.status == JobStatus.COMPLETED
    assert completed.url.endswith("/final")
    assert completed.title == "Worker result"
    assert statuses[-1] == "COMPLETED"


def test_worker_records_safe_fetch_failure(db, monkeypatch):
    job = job_crud.create_job(
        db, url="https://example.com/article", chunk_size=500, chunk_overlap=50
    )

    def reject(_):
        raise FetchError("UNSAFE_DESTINATION", "Destination is private.")

    monkeypatch.setattr("app.worker.tasks.fetch_public_html", reject)
    monkeypatch.setattr("app.worker.tasks.cache_job_status", lambda *args: None)

    outcome = ingest_document.run(job.id)

    db.expire_all()
    failed = job_crud.get_job(db, job.id)
    assert outcome["error"] == "UNSAFE_DESTINATION"
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == "UNSAFE_DESTINATION"


def test_worker_records_extraction_failure(db, monkeypatch):
    job = job_crud.create_job(
        db, url="https://example.com/article", chunk_size=500, chunk_overlap=50
    )
    monkeypatch.setattr(
        "app.worker.tasks.fetch_public_html",
        lambda _: FetchedPage("https://example.com", "<html></html>", "text/html"),
    )
    monkeypatch.setattr(
        "app.worker.tasks.extract_document",
        lambda *args: (_ for _ in ()).throw(ValueError("No readable content")),
    )
    monkeypatch.setattr("app.worker.tasks.cache_job_status", lambda *args: None)

    outcome = ingest_document.run(job.id)

    db.expire_all()
    assert outcome["status"] == "FAILED"
    assert job_crud.get_job(db, job.id).error_code == "EXTRACTION_FAILED"


def test_worker_handles_missing_job(monkeypatch):
    closed = []
    fake_db = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr("app.worker.tasks.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("app.worker.tasks.job_crud.get_job", lambda *args: None)

    assert ingest_document.run("missing") == {"job_id": "missing", "status": "NOT_FOUND"}
    assert closed == [True]


def test_worker_records_timeout_failure(db, monkeypatch):
    job = job_crud.create_job(
        db, url="https://example.com/article", chunk_size=500, chunk_overlap=50
    )

    def timeout(_):
        raise FetchError("TIMEOUT", "The request timed out.")

    monkeypatch.setattr("app.worker.tasks.fetch_public_html", timeout)
    monkeypatch.setattr("app.worker.tasks.cache_job_status", lambda *args: None)

    outcome = ingest_document.run(job.id)

    db.expire_all()
    failed = job_crud.get_job(db, job.id)
    assert outcome["error"] == "TIMEOUT"
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == "TIMEOUT"
