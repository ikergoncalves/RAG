"""PDF parser — one text block per page, carrying the page number."""

from pathlib import Path

from pypdf import PdfReader

from app.services.parsing.base import TextBlock


def parse(path: str | Path) -> list[TextBlock]:
    """Extract text from a PDF, one ``TextBlock`` per (non-empty) page."""
    reader = PdfReader(str(path))
    blocks: list[TextBlock] = []
    for index, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        blocks.append(TextBlock(text=text, page_number=index + 1))
    return blocks
