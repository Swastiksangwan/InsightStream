import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import DATABASE_URL
from app.core.database_safety import verify_test_connection

engine = create_engine(DATABASE_URL)

if os.getenv("INSIGHTSTREAM_ENV") == "test":
    @event.listens_for(engine, "connect")
    def verify_new_test_connection(dbapi_connection, _connection_record):
        try:
            verify_test_connection(dbapi_connection)
        finally:
            dbapi_connection.rollback()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
