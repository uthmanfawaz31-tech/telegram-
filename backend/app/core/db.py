from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models.models import Base

engine_args = {}
if "sqlite" in settings.SQLALCHEMY_DATABASE_URI:
    engine_args["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, **engine_args)

# Enable WAL journal mode and 30-second busy timeout for SQLite to handle concurrent reads & writes seamlessly
if "sqlite" in settings.SQLALCHEMY_DATABASE_URI:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
        except Exception:
            pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
