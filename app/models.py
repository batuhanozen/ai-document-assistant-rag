from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def identifier() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Metadata(Base):
    __tablename__ = "app_metadata"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    name: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int]
    page_count: Mapped[int | None]
    chunk_count: Mapped[int]
    status: Mapped[str] = mapped_column(String, default="indexing")
    uploaded_at: Mapped[str] = mapped_column(String, default=timestamp)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    chunks: Mapped[list["Chunk"]] = relationship(cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page: Mapped[int | None]
    text: Mapped[str] = mapped_column(Text)


class Chat(Base):
    __tablename__ = "chat_history"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=identifier)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    mode: Mapped[str]
    insufficient_context: Mapped[bool]
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String, default=timestamp)
