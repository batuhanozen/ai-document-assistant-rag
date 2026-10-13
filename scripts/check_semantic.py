"""Optional real-model integration check. Requires .[ai] and an initial model download."""

import math
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.database import create_database
from app.services.assistant import Assistant
from app.services.embeddings import SentenceTransformerEmbedder
from app.services.llm import DemoProvider
from app.services.vectors import VectorStore

embedder = SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
vectors = embedder.encode(
    [
        "How much paid time off can staff take?",
        "Employees receive 28 days of annual leave.",
        "The server runs on port 8000 and stores vectors in Chroma.",
    ]
)
assert len(vectors) == 3 and len(vectors[0]) == 384
assert all(math.isclose(sum(x * x for x in row), 1, abs_tol=1e-5) for row in vectors)
scores = [sum(a * b for a, b in zip(vectors[0], row, strict=True)) for row in vectors[1:]]
assert scores[0] > scores[1], scores
with TemporaryDirectory() as directory:
    settings = Settings(
        _env_file=None,
        data_dir=Path(directory),
        app_mode="demo",
        embedding_backend="sentence-transformers",
    )
    sessions = create_database(settings.data_dir)
    store = VectorStore(settings.data_dir / "chroma")
    assistant = Assistant(settings, sessions, embedder, store, DemoProvider())
    document = assistant.upload(b"Employees receive 28 days of annual leave.", "policy.txt")
    sources = assistant.retrieve("How much paid time off can staff take?", None)
    assert sources[0].citation.document_id == document.id
    assert "28 days" in sources[0].text
    assistant.delete(document.id)
    assert store.collection.count() == 0
    sessions.kw["bind"].dispose()
print(
    f"Semantic integration passed: 384 dimensions; paraphrase={scores[0]:.3f}, "
    f"unrelated={scores[1]:.3f}; Chroma retrieval and deletion verified."
)
