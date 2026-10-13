# Phase 1 architecture and implementation plan

The existing repository contained an MIT license and a Python .gitignore; both are retained.

1. Establish typed settings, SQLAlchemy persistence, domain errors, and API schemas.
2. Implement bounded TXT/PDF parsing, page-aware chunking, embedding adapters, and Chroma.
3. Implement ingestion/deletion state transitions, retrieval, verified citations, and history.
4. Add REST routes and a responsive, accessible, same-origin HTML/CSS/JavaScript interface.
5. Add synthetic examples and offline tests, including real Chroma integration and mocked HTTP.
6. Execute tests, lint, local HTTP/browser checks; document setup, tradeoffs, and Phase 2.

## Boundaries

- `app/api`: transport, streamed upload limits, schemas, status codes.
- `app/services/documents.py`: pure extraction and chunking.
- `app/services/embeddings.py`: Sentence Transformers and explicit offline lexical demo adapter.
- `app/services/vectors.py`: persistent Chroma with caller-supplied embeddings.
- `app/services/llm.py`: bounded HTTP provider, structured output, citation validation, demo excerpts.
- `app/services/assistant.py`: business workflows and SQLite/Chroma consistency.
- `app/models.py`, `app/database.py`: relational document/chunk/history persistence.
- `app/static`: same-origin frontend, no build pipeline or third-party JavaScript.

## Storage and consistency

SQLite is authoritative. Documents transition through `indexing → ready` or `failed`.
Chunks and metadata are committed before Chroma indexing. Only ready documents enter queries.
A failed indexing operation attempts vector cleanup and leaves a visible failed record.
Deletion first commits `deleting`, then removes vectors, then removes relational data.
Failed deletion remains retryable and excluded from retrieval. Startup marks interrupted
indexing as failed and retries cleanup of failed/deleting records. A process-level lock
serializes storage workflows; run exactly one application worker. Provider calls happen
outside that lock. Historical citations are snapshots; deleting a document also removes
history entries that reference it. In-flight answers are rejected if their documents were deleted.

Embedding identity and chunking settings are stored in a SQLite metadata row. A mismatch
fails startup rather than silently mixing embedding spaces. Use a new data directory when
changing model/backend/chunking; re-upload the original documents.

## Grounding

Retrieval uses cosine similarity and a configured minimum score. The demo offers verbatim
excerpts with lexical hashing retrieval, not semantic AI or generated answers. Full mode
uses Sentence Transformers and an OpenAI-compatible chat-completions endpoint. The provider
must return structured JSON with source IDs and exact quotes. Unknown IDs, missing citations,
and quotes absent from the corresponding retrieved chunk cause a safe abstention. This
verifies citation provenance, not logical entailment of every generated claim. The system
prompt marks documents as untrusted data; prompt injection defenses are best effort.

## Phase 1 scope

A local single-user tool, bound to loopback by default. No authentication, tenant isolation,
OCR, background queue, streaming generation, or production deployment is implied. Uploads
are raw bytes (not multipart), bounded while streaming before parsing, and never saved as
original files. Extracted text and question history are sensitive local data. PDF parsing
runs in a separate spawned process with a wall-clock timeout. Byte/page/text/chunk limits
bound routine workloads, but OS-level memory isolation is a future production requirement.
