import os

os.environ["DATABASE_URL"] = "sqlite:///./arachnin-test.db"
os.environ["REDIS_URL"] = "redis://localhost:6399/15"
os.environ["BROKER_URL"] = "memory://"
os.environ["RESULT_BACKEND_URL"] = "cache+memory://"

import httpx
import pytest

from app.api.deps import get_db
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.base_class import Base


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()
