import pytest

from app.errors import AppError
from app.services.documents import Page, chunk_pages, parse_document, parse_safely, safe_filename
from tests.conftest import make_pdf


def test_text_utf8_and_normalization(settings):
    result = parse_document("\ufeffCafé  handbook\r\nHello".encode(), "test.txt", settings)
    assert result.pages == [Page("Café handbook\nHello")]
    assert result.page_count is None


@pytest.mark.parametrize(
    "data,name,code",
    [
        (b"", "test.txt", "empty_file"),
        (b"  \n", "test.txt", "no_text"),
        (b"\xff\xfe", "test.txt", "invalid_text"),
        (b"binary\x00data", "test.txt", "invalid_text"),
        (b"not a pdf", "test.pdf", "invalid_pdf"),
        (b"%PDF-1.4 invalid body", "test.pdf", "invalid_pdf"),
    ],
)
def test_invalid_documents(settings, data, name, code):
    with pytest.raises(AppError) as failure:
        parse_document(data, name, settings)
    assert failure.value.code == code


def test_pdf_page_numbers_and_blank_warning(settings):
    result = parse_safely(make_pdf(["First page", None, "Third page"]), "test.pdf", settings)
    assert result.page_count == 3
    assert [page.number for page in result.pages] == [1, 3]
    assert result.pages[1].text == "Third page"
    assert "1 page(s)" in result.warnings[0]


@pytest.mark.parametrize(
    "texts,encrypted,code",
    [
        ([None], False, "no_text"),
        (["Secret"], True, "encrypted_pdf"),
    ],
)
def test_pdf_unsupported_cases(settings, texts, encrypted, code):
    with pytest.raises(AppError) as failure:
        parse_document(make_pdf(texts, encrypted), "test.pdf", settings)
    assert failure.value.code == code


def test_page_and_character_limits(settings):
    settings.max_pdf_pages = 1
    with pytest.raises(AppError, match="page limit"):
        parse_document(make_pdf(["First", "Second"]), "test.pdf", settings)
    settings.max_extracted_chars = 5
    with pytest.raises(AppError, match="text limit"):
        parse_document(b"too much text", "test.txt", settings)


def test_filename_safety():
    assert safe_filename("../../private/report.TXT") == "report.TXT"
    assert safe_filename("C:\\private\\report.pdf") == "report.pdf"
    with pytest.raises(AppError):
        safe_filename("report.exe")
    with pytest.raises(AppError):
        safe_filename("a" * 201 + ".txt")


def test_chunking_preserves_pages_bounds_and_coverage():
    text = "".join(chr(0x400 + i) for i in range(250))
    chunks = chunk_pages([Page(text, 2), Page("Final short page.", 3)], 80, 10)
    assert all(len(chunk.text) <= 80 for chunk in chunks)
    assert [chunk.number for chunk in chunks] == [2, 2, 2, 2, 3]
    reconstructed = chunks[0].text + "".join(c.text[10:] for c in chunks[1:4])
    assert reconstructed == text
    assert chunks[-1].text == "Final short page."


def test_chunking_prefers_boundaries():
    text = "A paragraph about annual leave.\n\n" + "Another sentence. " * 10
    chunks = chunk_pages([Page(text)], 60, 8)
    assert chunks[0].text == "A paragraph about annual leave."
    assert all(c.text for c in chunks)
    with pytest.raises(ValueError):
        chunk_pages([Page(text)], 20, 10)
