import sys
import types

import pytest

from app.services.embeddings import HashingEmbedder, SentenceTransformerEmbedder, build_embedder


class _Array:
    def __init__(self, rows):
        self.rows = rows

    def tolist(self):
        return self.rows


@pytest.fixture
def fake_sentence_transformers(monkeypatch):
    calls = {}

    class FakeModel:
        def __init__(self, name, revision=None, trust_remote_code=None):
            calls["init"] = {
                "name": name,
                "revision": revision,
                "trust_remote_code": trust_remote_code,
            }

        def encode(self, texts, **options):
            calls["encode"] = {"texts": texts, **options}
            return _Array([[1.0, 0.0] for _ in texts])

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = FakeModel
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    return calls


def test_sentence_transformer_adapter_options_and_identity(fake_sentence_transformers):
    embedder = SentenceTransformerEmbedder("org/model", "abc123")
    assert fake_sentence_transformers["init"] == {
        "name": "org/model",
        "revision": "abc123",
        "trust_remote_code": False,
    }
    assert embedder.identity == "sentence-transformers:org/model:abc123:normalized-v1"
    assert embedder.encode(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    options = fake_sentence_transformers["encode"]
    assert options["normalize_embeddings"] is True and options["show_progress_bar"] is False


def test_empty_revision_means_default_revision(fake_sentence_transformers):
    embedder = SentenceTransformerEmbedder("org/model")
    assert fake_sentence_transformers["init"]["revision"] is None
    assert ":default:" in embedder.identity


def test_build_embedder_selects_backend(settings, fake_sentence_transformers):
    assert isinstance(build_embedder(settings), HashingEmbedder)
    settings.embedding_backend = "sentence-transformers"
    assert isinstance(build_embedder(settings), SentenceTransformerEmbedder)
