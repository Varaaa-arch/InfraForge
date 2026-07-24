"""
Pytest configuration untuk test isolation.

Setiap test jalan di dalam 1 database transaction yang di-rollback setelah
selesai data test (user, project, dll) tidak numpuk di database asli, dan
test berikutnya tinggal pakai fixture `client` tanpa nulis ulang setup.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from loguru import logger

from app.config import settings
from app.database.session import get_db
from app.main import app

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """
    Buka koneksi + begin transaction.
    Semua operasi DB dalam test jalan di dalam transaction ini.
    Setelah test selesai, transaction di-rollback → DB tetap bersih.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient yang dependency get_db-nya di-override dengan
    db_session fixture di atas sehingga semua request dalam satu test
    share transaction yang sama dan ikut rollback bersama.
    """

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture()
def log_sink() -> Generator[list[str], None, None]:
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]), level="INFO") 
    yield messages
    logger.remove(sink_id)

