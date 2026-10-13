from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.schemas import AnswerResponse, DocumentResponse, QuestionRequest
from app.errors import AppError
from app.services.assistant import Assistant
from app.services.documents import safe_filename

router = APIRouter(prefix="/api")


def assistant(request: Request) -> Assistant:
    return request.app.state.assistant


Service = Annotated[Assistant, Depends(assistant)]


@router.get("/health")
def health(service: Service) -> dict:
    return {
        "status": "ok",
        "mode": service.settings.app_mode,
        "embedding_backend": service.settings.embedding_backend,
        "max_upload_mb": service.settings.max_upload_mb,
    }


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def upload_document(
    request: Request, service: Service, filename: str = Query(max_length=250)
):
    name = safe_filename(filename)
    content_type = request.headers.get("content-type", "").split(";")[0]
    if content_type not in {"application/pdf", "text/plain", "application/octet-stream"}:
        raise AppError(
            "unsupported_content_type", "Send raw PDF or TXT bytes, not multipart data.", 415
        )
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > service.settings.max_upload_mb * 1024 * 1024:
            raise AppError("upload_too_large", "The document exceeds the upload limit.", 413)
    return await run_in_threadpool(service.upload, bytes(data), name)


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(service: Service):
    return service.documents()


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: UUID, service: Service):
    service.delete(str(document_id))
    return Response(status_code=204)


@router.post("/questions", response_model=AnswerResponse)
def ask_question(payload: QuestionRequest, service: Service):
    ids = [str(value) for value in payload.document_ids] if payload.document_ids else None
    return service.ask(payload.question, ids)


@router.get("/history", response_model=list[AnswerResponse])
def history(service: Service, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return service.history(limit, offset)


@router.delete("/history", status_code=204)
def clear_history(service: Service):
    service.clear_history()
    return Response(status_code=204)
