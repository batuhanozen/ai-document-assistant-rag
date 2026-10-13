from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    size_bytes: int
    page_count: int | None
    chunk_count: int
    status: str
    uploaded_at: str
    warnings: list[str]


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[UUID] | None = Field(default=None, max_length=100)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = value.strip()
        if not value or "\x00" in value:
            raise ValueError("Question must contain text without null characters")
        return value

    @field_validator("document_ids")
    @classmethod
    def nonempty_selection(cls, value: list[UUID] | None) -> list[UUID] | None:
        if value == []:
            raise ValueError("Select at least one document or omit document_ids")
        return list(dict.fromkeys(value)) if value else value


class Citation(BaseModel):
    source_id: str
    document_id: str
    document_name: str
    chunk_id: str
    page: int | None
    quote: str
    similarity: float
    uploaded_at: str


class AnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    question: str
    answer: str
    mode: Literal["demo", "llm"]
    insufficient_context: bool
    citations: list[Citation]
    created_at: str
