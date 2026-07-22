"""
Pytest configuration untuk test isolation.
Override get_db dependency dengan SQLite in-memory sehingga tests tidak
memerlukan PostgreSQL running.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base, get_db
from app.main import app

SQLITE_URL = "sqlite://"  # in-memory, per-connection

engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # satu koneksi shared agar state tetap konsisten
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def db_session() -> None:
    """
    Setiap test mendapat database bersih (fresh schema) dengan SQLite in-memory.
    autouse=True agar berlaku untuk semua test tanpa perlu inject eksplisit.
    """
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db: Session = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    # Cleanup: drop semua tabel setelah test selesai
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
