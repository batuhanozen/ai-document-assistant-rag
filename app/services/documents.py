"""Bounded extraction and page-aware, character-based chunking."""

import multiprocessing
import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

from pypdf import PdfReader

from app.config import Settings
from app.errors import AppError


@dataclass(frozen=True)
class Page:
    text: str
    number: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    pages: list[Page]
    page_count: int | None
    warnings: list[str]


def safe_filename(filename: str) -> str:
    name = PurePosixPath(filename.replace("\\", "/")).name
    name = "".join(c for c in name if not unicodedata.category(c).startswith("C")).strip()
    if not name or len(name) > 200:
        raise AppError("invalid_filename", "Use a filename between 1 and 200 characters.")
    if PurePosixPath(name).suffix.lower() not in {".pdf", ".txt"}:
        raise AppError("unsupported_file", "Only PDF and UTF-8 TXT documents are supported.", 415)
    return name


def normalize(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_document(data: bytes, filename: str, settings: Settings) -> ParsedDocument:
    if not data:
        raise AppError("empty_file", "The uploaded file is empty.", 422)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError("upload_too_large", "The document exceeds the upload limit.", 413)
    if filename.lower().endswith(".txt"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AppError("invalid_text", "TXT documents must use UTF-8 encoding.", 422) from exc
        if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
            raise AppError("invalid_text", "The TXT file contains binary control characters.", 422)
        if len(text) > settings.max_extracted_chars:
            raise AppError("text_too_large", "The extracted text exceeds the text limit.", 413)
        result = ParsedDocument([Page(normalize(text))], None, [])
    else:
        if not data.startswith(b"%PDF-"):
            raise AppError("invalid_pdf", "This file does not have a valid PDF signature.", 422)
        try:
            reader = PdfReader(BytesIO(data), strict=False)
            if reader.is_encrypted:
                raise AppError("encrypted_pdf", "Password-protected PDFs are not supported.", 422)
            if len(reader.pages) > settings.max_pdf_pages:
                raise AppError("too_many_pages", "The PDF exceeds the page limit.", 413)
            pages = []
            total = 0
            blank = 0
            for number, page in enumerate(reader.pages, start=1):
                text = normalize(page.extract_text() or "")
                total += len(text)
                if total > settings.max_extracted_chars:
                    raise AppError(
                        "text_too_large", "The extracted text exceeds the text limit.", 413
                    )
                if text:
                    pages.append(Page(text, number))
                else:
                    blank += 1
            warnings = (
                [f"{blank} page(s) had no extractable text; OCR is not available."] if blank else []
            )
            result = ParsedDocument(pages, len(reader.pages), warnings)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                "invalid_pdf", "The PDF could not be read. Try exporting it again.", 422
            ) from exc
    if not any(page.text for page in result.pages):
        raise AppError(
            "no_text", "No text could be extracted. Image-only PDFs need OCR before upload.", 422
        )
    return result


def _parse_worker(connection, data: bytes, filename: str, config: dict) -> None:
    try:
        result = parse_document(data, filename, Settings(_env_file=None, **config))
        connection.send(("ok", result))
    except AppError as exc:
        connection.send(("error", (exc.code, exc.message, exc.status)))
    except Exception:
        connection.send(("error", ("invalid_pdf", "The document could not be parsed.", 422)))
    finally:
        connection.close()


def parse_safely(data: bytes, filename: str, settings: Settings) -> ParsedDocument:
    if filename.lower().endswith(".txt"):
        return parse_document(data, filename, settings)
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    # Do not send provider credentials to the parser subprocess.
    config = settings.model_dump(exclude={"llm_api_key", "app_mode"})
    config["app_mode"] = "demo"
    process = context.Process(
        target=_parse_worker, args=(sender, data, filename, config), daemon=True
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(settings.parsing_timeout_seconds):
            raise AppError("parsing_timeout", "Document parsing timed out. Try a smaller PDF.", 422)
        try:
            status, payload = receiver.recv()
        except EOFError as exc:
            raise AppError("invalid_pdf", "The PDF parser could not finish.", 422) from exc
        if status == "error":
            raise AppError(*payload)
        return payload
    finally:
        receiver.close()
        process.join(timeout=0.2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join()
        process.close()


def chunk_pages(pages: list[Page], size: int, overlap: int) -> list[Page]:
    if size < 1 or overlap < 0 or overlap >= size / 2:
        raise ValueError("Chunk size must be positive and overlap less than half the size")
    chunks = []
    for page in pages:
        text = normalize(page.text)
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                # Prefer paragraphs, then sentences, then word boundaries in the latter half.
                floor = start + size // 2
                for separator in ("\n\n", ". ", "\n", " "):
                    boundary = text.rfind(separator, floor, end)
                    if boundary != -1:
                        end = boundary + len(separator)
                        break
            value = text[start:end].strip()
            if value:
                chunks.append(Page(value, page.number))
            if end == len(text):
                break
            start = end - overlap
    return chunks
