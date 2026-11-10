from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base


def create_database(data_dir: Path) -> sessionmaker[Session]:
    data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{data_dir.resolve() / 'assistant.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _add_missing_columns(engine) -> None:
    """Upgrade data directories created before ``documents.content_hash`` existed."""
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(documents)")}
        if "content_hash" not in columns:
            connection.exec_driver_sql("ALTER TABLE documents ADD COLUMN content_hash VARCHAR(64)")
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_documents_content_hash ON documents (content_hash)"
            )
