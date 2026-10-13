from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    def __init__(self, directory: Path):
        self.client = chromadb.PersistentClient(
            path=str(directory), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            "document_chunks", embedding_function=None, configuration={"hnsw": {"space": "cosine"}}
        )

    def add(self, ids: list[str], document_id: str, embeddings: list[list[float]]) -> None:
        for start in range(0, len(ids), 100):
            batch_ids = ids[start : start + 100]
            self.collection.upsert(
                ids=batch_ids,
                embeddings=embeddings[start : start + 100],
                metadatas=[{"document_id": document_id} for _ in batch_ids],
            )

    def delete(self, document_id: str) -> None:
        self.collection.delete(where={"document_id": document_id})

    def search(
        self, embedding: list[float], document_ids: list[str], limit: int
    ) -> list[tuple[str, float]]:
        if not document_ids or self.collection.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[embedding],
            where={"document_id": {"$in": document_ids}},
            n_results=min(limit, self.collection.count()),
            include=["distances"],
        )
        ids = result["ids"][0]
        distances = (result["distances"] or [[]])[0]
        return [
            (chunk_id, max(-1.0, min(1.0, 1 - d)))
            for chunk_id, d in zip(ids, distances, strict=True)
        ]
