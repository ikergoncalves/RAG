"""HTML parser — block elements grouped under their ``h1``-``h6`` breadcrumb."""

import re
from pathlib import Path

from bs4 import BeautifulSoup

from app.services.parsing.base import SectionPathTracker, TextBlock

_HEADING_RE = re.compile(r"^h([1-6])$")
_BLOCK_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]


def parse(path: str | Path) -> list[TextBlock]:
    html = Path(path).read_text(encoding="utf-8")
    return parse_text(html)


def parse_text(html: str) -> list[TextBlock]:
    soup = BeautifulSoup(html, "html.parser")
    tracker = SectionPathTracker()
    blocks: list[TextBlock] = []

    # find_all yields elements in document order, so the breadcrumb stays in sync.
    for element in soup.find_all(_BLOCK_TAGS):
        text = element.get_text(" ", strip=True)
        if not text:
            continue

        heading_match = _HEADING_RE.match(element.name)
        if heading_match:
            tracker.update(int(heading_match.group(1)), text)
            continue

        blocks.append(TextBlock(text=text, section_path=tracker.path()))

    return blocks
