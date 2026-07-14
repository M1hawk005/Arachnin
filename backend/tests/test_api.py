import pytest

from app.crud import job_crud
from app.models.job import JobStatus

pytestmark = pytest.mark.anyio


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "arachnin-api"}


async def test_ingestion_lifecycle(client, db, monkeypatch):
    monkeypatch.setattr("app.api.routers.extract.validate_public_url", lambda _: None)
    queued = []
    monkeypatch.setattr("app.api.routers.extract.ingest_document.delay", queued.append)

    created = await client.post(
        "/api/v1/ingestions",
        json={"url": "https://example.com/article", "chunk_size": 300, "chunk_overlap": 30},
    )

    assert created.status_code == 202
    job_id = created.json()["job_id"]
    assert queued == [job_id]
    assert created.json()["status_url"].endswith(job_id)

    status = await client.get(f"/api/v1/ingestions/{job_id}")
    assert status.json()["progress"] == 10

    job = job_crud.get_job(db, job_id)
    job.status = JobStatus.COMPLETED
    job.title = "An article"
    job.content = "Useful retrieval content"
    job.content_hash = "a" * 64
    job.word_count = 3
    job.chunks = [{"index": 0, "text": job.content, "word_count": 3}]
    db.commit()

    result = await client.get(f"/api/v1/ingestions/{job_id}/result")
    assert result.status_code == 200
    assert result.json()["metadata"]["title"] == "An article"
    assert result.json()["chunks"][0]["index"] == 0

    recent = await client.get("/api/v1/ingestions")
    assert recent.status_code == 200
    assert recent.json()[0]["chunk_count"] == 1


async def test_ingestion_validation_error(client, monkeypatch):
    from app.services.security import FetchError

    def reject(_: str):
        raise FetchError("UNSAFE_DESTINATION", "Private networks are blocked.")

    monkeypatch.setattr("app.api.routers.extract.validate_public_url", reject)
    response = await client.post("/api/v1/ingestions", json={"url": "http://localhost/article"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNSAFE_DESTINATION"


async def test_missing_and_incomplete_results(client, db):
    missing = await client.get("/api/v1/ingestions/does-not-exist")
    assert missing.status_code == 404

    job = job_crud.create_job(db, url="https://example.com", chunk_size=500, chunk_overlap=50)
    incomplete = await client.get(f"/api/v1/ingestions/{job.id}/result")
    assert incomplete.status_code == 409


async def test_queue_failure_is_explicit(client, monkeypatch):
    monkeypatch.setattr("app.api.routers.extract.validate_public_url", lambda _: None)

    def fail(_: str):
        raise ConnectionError("broker down")

    monkeypatch.setattr("app.api.routers.extract.ingest_document.delay", fail)
    response = await client.post("/api/v1/ingestions", json={"url": "https://example.com"})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "QUEUE_UNAVAILABLE"
