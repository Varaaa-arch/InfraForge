from collections.abc import Generator
from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from app.config import settings 

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase): 
    pass 

def get_db() -> Generator[Session, None, None]: 
    db: Session = SessionLocal()
    try:
        yield db
    finally: 
        db.close()

def check_database_connection() -> bool:
    try: 
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("Database connection successful.")
            return True
    except Exception as e:
        logger.warning(f"Database connection failed: {e}") 
        return False
            

