import json
import math
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.embeddings import HashingEmbedder


def test_hash_embeddings_deterministic_and_normalized():
    embedder = HashingEmbedder()
    vector = embedder.encode(["Annual leave leave policy"])[0]
    assert vector == HashingEmbedder().encode(["Annual leave leave policy"])[0]
    assert math.isclose(sum(v * v for v in vector), 1)
    assert embedder.encode(["the and is"])[0] == [0.0] * 2048


def test_demo_acceptance_cases(client):
    root = Path(__file__).resolve().parents[1]
    for name in ["atlas-handbook.txt", "aurora-project.txt"]:
        result = client.post(
            f"/api/documents?filename={name}",
            content=(root / "app/static/examples" / name).read_bytes(),
            headers={"Content-Type": "text/plain"},
        )
        assert result.status_code == 201
    for case in json.loads((root / "examples/test-cases.json").read_text()):
        answer = client.post("/api/questions", json={"question": case["question"]}).json()
        assert answer["insufficient_context"] == case["insufficient_context"], case["question"]
        assert case["expected_text"] in answer["answer"]
        if case["document"]:
            assert case["document"] in [c["document_name"] for c in answer["citations"]]


def test_data_survives_restart(settings):
    with TestClient(create_app(settings), base_url="http://localhost") as first:
        result = first.post(
            "/api/documents?filename=policy.txt",
            content=b"Annual leave is 28 days.",
            headers={"Content-Type": "text/plain"},
        )
        assert result.status_code == 201
    with TestClient(create_app(settings), base_url="http://localhost") as second:
        assert len(second.get("/api/documents").json()) == 1
        answer = second.post("/api/questions", json={"question": "annual leave"}).json()
        assert "28 days" in answer["answer"]
