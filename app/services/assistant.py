import hashlib
import json
import logging
from threading import RLock

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.schemas import AnswerResponse, Citation, DocumentResponse
from app.config import Settings
from app.errors import AppError
from app.models import Chat, Chunk, Document, Metadata, identifier
from app.services.documents import chunk_pages, parse_safely, safe_filename
from app.services.embeddings import Embedder
from app.services.llm import ABSTENTION, GeneratedAnswer, Provider, Source
from app.services.vectors import VectorStore

logger = logging.getLogger(__name__)

ENCODE_BATCH_SIZE = 32


class Assistant:
    def __init__(
        self,
        settings: Settings,
        sessions: sessionmaker[Session],
        embedder: Embedder,
        vectors: VectorStore,
        provider: Provider,
    ):
        self.settings = settings
        self.sessions = sessions
        self.embedder = embedder
        self.vectors = vectors
        self.provider = provider
        # ``lock`` serializes SQLite/Chroma workflows; ``encode_lock`` serializes the embedder,
        # which may not be thread-safe, without holding ``lock`` during slow model inference.
        self.lock = RLock()
        self.encode_lock = RLock()
        self._initialize()

    def _initialize(self) -> None:
        fingerprint = json.dumps(
            {
                "embedding": self.embedder.identity,
                "chunk_size": self.settings.chunk_size,
                "overlap": self.settings.chunk_overlap,
                "schema": 1,
            },
            sort_keys=True,
        )
        with self.sessions.begin() as session:
            stored = session.get(Metadata, "index_configuration")
            if stored and stored.value != fingerprint:
                raise RuntimeError(
                    "Index configuration changed. Use a new DATA_DIR and re-upload documents."
                )
            if not stored:
                session.add(Metadata(key="index_configuration", value=fingerprint))
            interrupted = session.scalars(select(Document).where(Document.status == "indexing"))
            for document in interrupted:
                document.status = "failed"
        with self.sessions() as session:
            pending = [
                (d.id, d.status)
                for d in session.scalars(
                    select(Document).where(Document.status.in_(["failed", "deleting"]))
                )
            ]
        for document_id, status in pending:
            try:
                if status == "deleting":
                    self.delete(document_id)
                else:
                    self.vectors.delete(document_id)
            except Exception:
                logger.warning("Storage recovery deferred for document %s", document_id)

    def documents(self) -> list[DocumentResponse]:
        with self.sessions() as session:
            return [
                DocumentResponse.model_validate(d)
                for d in session.scalars(select(Document).order_by(Document.uploaded_at.desc()))
            ]

    def check_storage(self) -> None:
        """Raise if either the relational or the vector store cannot be reached."""
        try:
            with self.sessions() as session:
                session.execute(select(Metadata.key).limit(1)).all()
            self.vectors.collection.count()
        except Exception as exc:
            logger.error("Storage health check failed (%s)", type(exc).__name__)
            raise AppError(
                "storage_unavailable", "Document storage is temporarily unavailable.", 503
            ) from exc

    def _encode(self, texts: list[str]) -> list[list[float]]:
        # Encode in small batches so a large upload does not starve question embedding.
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), ENCODE_BATCH_SIZE):
            with self.encode_lock:
                embeddings.extend(self.embedder.encode(texts[start : start + ENCODE_BATCH_SIZE]))
        return embeddings

    @staticmethod
    def _reject_duplicate(session: Session, digest: str) -> None:
        existing = session.scalar(
            select(Document.name).where(
                Document.content_hash == digest, Document.status.in_(["indexing", "ready"])
            )
        )
        if existing:
            raise AppError(
                "duplicate_document",
                f"This document is already in your library as \u201c{existing}\u201d.",
                409,
            )

    def upload(self, data: bytes, filename: str) -> DocumentResponse:
        name = safe_filename(filename)
        digest = hashlib.sha256(data).hexdigest()
        # Early, best-effort check so duplicates do not pay for parsing; re-checked under the lock.
        with self.sessions() as session:
            self._reject_duplicate(session, digest)
        parsed = parse_safely(data, name, self.settings)
        chunks = chunk_pages(parsed.pages, self.settings.chunk_size, self.settings.chunk_overlap)
        if len(chunks) > self.settings.max_chunks:
            raise AppError("too_many_chunks", "The document contains too many text chunks.", 413)
        document_id = identifier()
        rows = [
            Chunk(id=f"{document_id}:{i}", document_id=document_id, page=c.number, text=c.text)
            for i, c in enumerate(chunks)
        ]
        with self.lock, self.sessions.begin() as session:
            self._reject_duplicate(session, digest)
            session.add(
                Document(
                    id=document_id,
                    name=name,
                    size_bytes=len(data),
                    page_count=parsed.page_count,
                    chunk_count=len(chunks),
                    content_hash=digest,
                    warnings=parsed.warnings,
                    chunks=rows,
                )
            )
        try:
            embeddings = self._encode([c.text for c in chunks])
            with self.lock:
                self.vectors.add([row.id for row in rows], document_id, embeddings)
                with self.sessions.begin() as session:
                    stored = session.get(Document, document_id)
                    stored.status = "ready"
                    session.flush()
                    result = DocumentResponse.model_validate(stored)
        except Exception as exc:
            with self.lock:
                with self.sessions.begin() as session:
                    session.get(Document, document_id).status = "failed"
                try:
                    self.vectors.delete(document_id)
                except Exception:
                    logger.warning("Vector cleanup pending for document %s", document_id)
            logger.error("Document indexing failed (%s)", type(exc).__name__)
            raise AppError(
                "indexing_failed", "Indexing failed. Delete the failed entry and retry.", 503
            ) from exc
        logger.info("Document indexed: %s (%d chunks)", document_id, len(chunks))
        return result

    def delete(self, document_id: str) -> None:
        with self.lock:
            with self.sessions.begin() as session:
                document = session.get(Document, document_id)
                if not document:
                    raise AppError("document_not_found", "Document not found.", 404)
                if document.status == "indexing":
                    raise AppError(
                        "document_busy", "The document is still being indexed. Try again soon.", 409
                    )
                document.status = "deleting"
            try:
                self.vectors.delete(document_id)
            except Exception as exc:
                raise AppError(
                    "deletion_failed", "Vector deletion failed. Please retry deletion.", 503
                ) from exc
            with self.sessions.begin() as session:
                # History snapshots also contain document text; remove affected answers.
                # json_each keeps the scan inside SQLite instead of loading every answer.
                session.execute(
                    text(
                        "DELETE FROM chat_history WHERE EXISTS (SELECT 1 FROM "
                        "json_each(chat_history.citations) "
                        "WHERE json_extract(json_each.value, '$.document_id') = :document_id)"
                    ),
                    {"document_id": document_id},
                )
                session.delete(session.get(Document, document_id))
        logger.info("Document deleted: %s", document_id)

    def retrieve(self, question: str, document_ids: list[str] | None) -> list[Source]:
        with self.lock, self.sessions() as session:
            documents = list(session.scalars(select(Document).where(Document.status == "ready")))
            available = {d.id: d for d in documents}
            if document_ids and not set(document_ids).issubset(available):
                raise AppError(
                    "document_not_ready", "One or more selected documents are unavailable.", 404
                )
            selected = document_ids if document_ids is not None else list(available)
            if not selected:
                return []
            try:
                hits = self.vectors.search(
                    self._encode([question])[0], selected, self.settings.retrieval_top_k
                )
            except Exception as exc:
                raise AppError(
                    "retrieval_failed", "Document search is temporarily unavailable.", 503
                ) from exc
            sources = []
            remaining = self.settings.max_context_chars
            for chunk_id, score in hits:
                if score < self.settings.min_similarity:
                    continue
                chunk = session.get(Chunk, chunk_id)
                if not chunk or chunk.document_id not in selected:
                    continue
                document = available[chunk.document_id]
                text = chunk.text[:remaining]
                if not text:
                    break
                remaining -= len(text)
                sources.append(
                    Source(
                        Citation(
                            source_id=f"S{len(sources) + 1}",
                            document_id=document.id,
                            document_name=document.name,
                            chunk_id=chunk.id,
                            page=chunk.page,
                            quote="",
                            similarity=round(score, 4),
                            uploaded_at=document.uploaded_at,
                        ),
                        text,
                    )
                )
            return sources

    def ask(self, question: str, document_ids: list[str] | None = None) -> AnswerResponse:
        sources = self.retrieve(question, document_ids)
        generated = (
            self.provider.generate(question, sources)
            if sources
            else GeneratedAnswer(ABSTENTION, [], True)
        )
        with self.lock, self.sessions.begin() as session:
            for source in sources:
                document = session.get(Document, source.citation.document_id)
                if not document or document.status != "ready":
                    raise AppError(
                        "documents_changed", "Documents changed during this answer. Try again.", 409
                    )
            chat = Chat(
                question=question,
                answer=generated.answer,
                mode=self.settings.app_mode,
                insufficient_context=generated.insufficient_context,
                citations=[c.model_dump() for c in generated.citations],
            )
            session.add(chat)
            session.flush()
            return AnswerResponse.model_validate(chat)

    def history(self, limit: int = 50, offset: int = 0) -> list[AnswerResponse]:
        with self.sessions() as session:
            rows = session.scalars(
                select(Chat).order_by(Chat.created_at.desc()).offset(offset).limit(limit)
            )
            return [AnswerResponse.model_validate(row) for row in rows]

    def clear_history(self) -> None:
        with self.lock, self.sessions.begin() as session:
            for row in session.scalars(select(Chat)):
                session.delete(row)
