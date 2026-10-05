import pytest
import pytest_asyncio
import anyio.to_thread
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.routers import sounds
import app.models  # noqa: F401


@pytest.fixture(autouse=True)
def isolated_audio_cache(tmp_path, monkeypatch):
    """Keep tests off the network and away from the developer's real audio cache."""
    monkeypatch.setattr(settings, "audio_cache_dir", str(tmp_path / "audio-cache"))
    monkeypatch.setattr(settings, "audio_extraction_enabled", False)


@pytest.fixture(autouse=True)
def disable_rate_limits(monkeypatch):
    """The in-memory limiter is shared across tests in one process."""
    monkeypatch.setattr(sounds.limiter, "enabled", False)


@pytest_asyncio.fixture
async def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    async def run_sync_inline(function, *args, **_kwargs):
        # The restricted execution container cannot create AnyIO worker threads.
        return function(*args)

    monkeypatch.setattr(anyio.to_thread, "run_sync", run_sync_inline)
    fastapi_app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://testserver") as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()
