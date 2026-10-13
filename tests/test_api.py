from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Document
from tests.conftest import make_pdf


def test_document_question_history_delete_lifecycle(client, upload):
    response = upload()
    assert response.status_code == 201
    doc = response.json()
    assert doc["status"] == "ready" and doc["chunk_count"] == 1
    assert client.get("/api/documents").json()[0]["id"] == doc["id"]
    response = client.post("/api/questions", json={"question": "How many annual leave days?"})
    assert response.status_code == 200
    answer = response.json()
    assert answer["mode"] == "demo"
    assert "28 days" in answer["answer"]
    citation = answer["citations"][0]
    assert citation["document_id"] == doc["id"]
    assert citation["chunk_id"].startswith(doc["id"])
    assert citation["page"] is None
    assert citation["quote"] == "Employees receive 28 days of paid annual leave."
    assert client.get("/api/history").json()[0]["id"] == answer["id"]
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204
    assert client.get("/api/documents").json() == []
    assert client.get("/api/history").json() == []
    assert client.app.state.assistant.vectors.collection.count() == 0
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 404


def test_pdf_upload_citations(client):
    response = client.post(
        "/api/documents?filename=brief.pdf",
        content=make_pdf([None, "Aurora starts in November."]),
        headers={"Content-Type": "application/pdf"},
    )
    assert response.status_code == 201
    assert response.json()["warnings"]
    answer = client.post("/api/questions", json={"question": "When does Aurora start?"}).json()
    assert answer["citations"][0]["page"] == 2
    assert answer["citations"][0]["document_name"] == "brief.pdf"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": " "},
        {"question": "x" * 2001},
        {"question": "hi", "document_ids": []},
        {"question": "hi", "document_ids": ["not-a-uuid"]},
        {"question": "hi", "unexpected": True},
    ],
)
def test_question_validation(client, payload):
    response = client.post("/api/questions", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert set(response.json()["error"]) == {"code", "message"}


def test_no_context_abstains_without_provider_call(client, monkeypatch):
    def fail(*args):
        raise AssertionError("Provider should not be called")

    monkeypatch.setattr(client.app.state.assistant.provider, "generate", fail)
    answer = client.post("/api/questions", json={"question": "What is the answer?"}).json()
    assert answer["insufficient_context"] is True
    assert answer["citations"] == []


def test_selection_is_enforced(client, upload):
    first = upload("The vacation allowance is 28 days.", "one.txt").json()
    second = upload("The vacation allowance is 15 days.", "two.txt").json()
    answer = client.post(
        "/api/questions",
        json={"question": "What is the vacation allowance?", "document_ids": [second["id"]]},
    ).json()
    assert {c["document_id"] for c in answer["citations"]} == {second["id"]}
    assert first["id"] != second["id"]
    missing = client.post(
        "/api/questions", json={"question": "vacation", "document_ids": [str(uuid4())]}
    )
    assert missing.status_code == 404


def test_upload_errors_and_size_limits(client, settings):
    assert (
        client.post(
            "/api/documents?filename=file.exe",
            content=b"hello",
            headers={"Content-Type": "application/octet-stream"},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/documents?filename=file.txt",
            content=b"hello",
            headers={"Content-Type": "multipart/form-data"},
        ).status_code
        == 415
    )
    assert (
        client.post(
            "/api/documents?filename=file.txt", content=b"", headers={"Content-Type": "text/plain"}
        ).status_code
        == 422
    )
    large = client.post(
        "/api/documents?filename=file.txt",
        content=b"x",
        headers={"Content-Type": "text/plain", "Content-Length": str(11 * 1024 * 1024)},
    )
    assert large.status_code == 413
    # Exercise the streaming cap independently of the Content-Length header.
    large_stream = client.post(
        "/api/documents?filename=file.txt",
        content=iter([b"x" * (settings.max_upload_mb * 1024 * 1024 + 1)]),
        headers={"Content-Type": "text/plain"},
    )
    assert large_stream.status_code == 413
    assert client.post("/api/questions", content=b"x" * 16385).status_code == 413


def test_security_headers_origin_and_input_not_rendered(client, upload):
    response = client.get("/")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    assert (
        client.delete("/api/history", headers={"Origin": "https://evil.example"}).status_code == 403
    )
    assert client.delete("/api/history", headers={"Origin": "http://localhost"}).status_code == 204
    assert upload("<script>alert('xss')</script> vacation policy").status_code == 201
    script = client.get("/static/app.js").text
    assert "innerHTML" not in script
    assert "textContent" in script


def test_indexing_failure_is_excluded_and_visible(client, upload, monkeypatch):
    service = client.app.state.assistant

    def fail(*args):
        raise RuntimeError("private provider details")

    monkeypatch.setattr(service.vectors, "add", fail)
    response = upload()
    assert response.status_code == 503
    assert "private" not in response.text
    assert client.get("/api/documents").json()[0]["status"] == "failed"
    assert service.retrieve("annual leave", None) == []


def test_failed_delete_retry(client, upload, monkeypatch):
    service = client.app.state.assistant
    doc = upload().json()
    original = service.vectors.delete

    def fail(*args):
        raise RuntimeError("disk failure")

    monkeypatch.setattr(service.vectors, "delete", fail)
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 503
    assert client.get("/api/documents").json()[0]["status"] == "deleting"
    assert service.retrieve("annual leave", None) == []
    monkeypatch.setattr(service.vectors, "delete", original)
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 204


def test_history_pagination_and_clear(client):
    for question in ["First?", "Second?", "Third?"]:
        assert client.post("/api/questions", json={"question": question}).status_code == 200
    assert client.get("/api/history?limit=1&offset=1").json()[0]["question"] == "Second?"
    assert client.get("/api/history?limit=101").status_code == 422
    assert client.delete("/api/history").status_code == 204
    assert client.get("/api/history").json() == []


def test_delete_during_generation_rejects_stale_answer(client, upload, monkeypatch):
    service = client.app.state.assistant
    doc = upload().json()
    original = service.provider.generate

    def deleting_provider(question, sources):
        result = original(question, sources)
        service.delete(doc["id"])
        return result

    monkeypatch.setattr(service.provider, "generate", deleting_provider)
    assert client.post("/api/questions", json={"question": "annual leave days"}).status_code == 409
    assert client.get("/api/history").json() == []


def test_startup_recovers_interrupted_indexing(client, upload):
    service = client.app.state.assistant
    upload()
    with service.sessions.begin() as session:
        session.scalar(select(Document)).status = "indexing"
    service._initialize()
    assert service.documents()[0].status == "failed"
    assert service.vectors.collection.count() == 0


def test_index_configuration_mismatch_fails(client):
    service = client.app.state.assistant
    service.settings.chunk_size += 1
    with pytest.raises(RuntimeError, match="configuration changed"):
        service._initialize()


@pytest.mark.parametrize(
    "origin", ["https://localhost", "http://[", "null", "http://localhost/path"]
)
def test_invalid_or_cross_scheme_origins_are_rejected(client, origin):
    response = client.delete("/api/history", headers={"Origin": origin})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_rejected"


def test_non_ascii_unrelated_header_does_not_crash(client):
    response = client.get("/api/health", headers={b"X-Display-Name": b"caf\xe9"})
    assert response.status_code == 200
