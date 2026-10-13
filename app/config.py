from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: Literal["demo", "llm"] = "demo"
    embedding_backend: Literal["hashing", "sentence-transformers"] = "hashing"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = ""
    data_dir: Path = Path("data")
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_seconds: float = Field(default=45, ge=1, le=180)
    max_upload_mb: int = Field(default=10, ge=1, le=50)
    max_pdf_pages: int = Field(default=200, ge=1, le=1000)
    parsing_timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_extracted_chars: int = Field(default=500_000, ge=1000, le=2_000_000)
    max_chunks: int = Field(default=2000, ge=1, le=5000)
    chunk_size: int = Field(default=700, ge=200, le=2000)
    chunk_overlap: int = Field(default=120, ge=0)
    retrieval_top_k: int = Field(default=5, ge=1, le=10)
    min_similarity: float = Field(default=0.2, ge=0, le=1)
    max_context_chars: int = Field(default=6000, ge=2000, le=20000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size // 2:
            raise ValueError("CHUNK_OVERLAP must be less than half of CHUNK_SIZE")
        if self.app_mode == "llm" and self.embedding_backend != "sentence-transformers":
            raise ValueError("LLM mode requires EMBEDDING_BACKEND=sentence-transformers")
        url = urlparse(self.llm_base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("LLM_BASE_URL must be an HTTP(S) URL without credentials")
        if url.query or url.fragment:
            raise ValueError("LLM_BASE_URL must not have a query or fragment")
        if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Non-local LLM endpoints must use HTTPS")
        if self.app_mode == "llm" and not self.llm_api_key.get_secret_value():
            if url.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("LLM_API_KEY is required for a remote provider")
        return self
