"""DOCX parser — paragraphs grouped under their heading breadcrumb.

Headings are detected by paragraph style name (``Heading 1``, ``Heading 2``,
...). Word does not expose page numbers without rendering, so ``page_number``
stays ``None``.
"""

import re
from pathlib import Path

from docx import Document as DocxDocument

from app.services.parsing.base import SectionPathTracker, TextBlock

_HEADING_RE = re.compile(r"^Heading\s+(\d+)$", re.IGNORECASE)


def parse(path: str | Path) -> list[TextBlock]:
    document = DocxDocument(str(path))
    tracker = SectionPathTracker()
    blocks: list[TextBlock] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style_name = paragraph.style.name if paragraph.style else ""
        heading_match = _HEADING_RE.match(style_name or "")
        if heading_match:
            tracker.update(int(heading_match.group(1)), text)
            continue

        blocks.append(TextBlock(text=text, section_path=tracker.path()))

    return blocks
