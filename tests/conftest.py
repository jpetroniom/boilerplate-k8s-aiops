import pytest
from datetime import UTC, datetime


def make_event(
    uid="u1",
    type="Warning",
    reason="BackOff",
    note="msg",
    namespace="default",
    series_last=None,
    event_time=None,
    deprecated_last=None,
    regarding=None,
):
    return {
        "metadata": {"uid": uid, "namespace": namespace},
        "type": type,
        "reason": reason,
        "note": note,
        "regarding": regarding or {"kind": "Pod", "name": "p", "namespace": namespace},
        "series": {"lastObservedTime": series_last} if series_last else None,
        "eventTime": event_time,
        "deprecatedLastTimestamp": deprecated_last,
    }


def ts(minute, second=0):
    return datetime(2026, 1, 1, 12, minute, second, tzinfo=UTC)


def iso(minute, second=0):
    return ts(minute, second).strftime("%Y-%m-%dT%H:%M:%S.000000Z")


import os  # noqa: E402

import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://aiops:aiops123@localhost:5432/aiops_k8s_test"
)
ADMIN_DATABASE_URL = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"


@pytest_asyncio.fixture
async def sessionmaker():
    """Banco de teste dedicado no PostgreSQL do compose; pula se indisponivel."""
    from my_agent_app import models  # noqa: F401
    from my_agent_app.database import Base

    name = TEST_DATABASE_URL.rsplit("/", 1)[1]
    try:
        admin = create_async_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
        async with admin.connect() as conn:
            exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name})
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{name}"'))
        await admin.dispose()
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # banco indisponivel
        pytest.skip(f"PostgreSQL indisponivel: {exc}")
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
