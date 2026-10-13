import hashlib
import math
import re
from collections import Counter
from typing import Protocol

from app.config import Settings

STOP_WORDS = frozenset(
    "a an the is are was were be been to of and or in on at for from with as by it its "
    "what which who when where how do does did can could would should i we you they "
    "this that these those me my your our their about please tell".split()
)


def terms(text: str) -> list[str]:
    return [word for word in re.findall(r"\w+", text.lower()) if word not in STOP_WORDS]


class Embedder(Protocol):
    @property
    def identity(self) -> str: ...
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Offline, deterministic lexical baseline. This is NOT a semantic language model."""

    identity = "hashing-v1-2048"

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 2048
            for token, count in Counter(terms(text)).items():
                digest = hashlib.sha256(token.encode()).digest()
                index = int.from_bytes(digest[:4], "big") % len(vector)
                vector[index] += (1 + math.log(count)) * (1 if digest[4] % 2 else -1)
            norm = math.sqrt(sum(x * x for x in vector)) or 1
            vectors.append([x / norm for x in vector])
        return vectors


class SentenceTransformerEmbedder:
    def __init__(self, model: str, revision: str = ""):
        from sentence_transformers import SentenceTransformer

        self.identity = f"sentence-transformers:{model}:{revision or 'default'}:normalized-v1"
        self.model = SentenceTransformer(model, revision=revision or None, trust_remote_code=False)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32
        ).tolist()


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_backend == "hashing":
        return HashingEmbedder()
    return SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_revision)
