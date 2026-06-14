"""Markdown parser — paragraphs grouped under their ATX heading breadcrumb.

Uses ``markdown-it-py`` to tokenize, then walks the token stream: ``heading_open``
tokens (``h1``..``h6``) update the section breadcrumb and ``paragraph`` tokens
become text blocks.
"""

from pathlib import Path

from markdown_it import MarkdownIt

from app.services.parsing.base import SectionPathTracker, TextBlock


def parse(path: str | Path) -> list[TextBlock]:
    text = Path(path).read_text(encoding="utf-8")
    return parse_text(text)


def parse_text(text: str) -> list[TextBlock]:
    md = MarkdownIt()
    tokens = md.parse(text)
    tracker = SectionPathTracker()
    blocks: list[TextBlock] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        # heading_open -> inline (content) -> heading_close
        if token.type == "heading_open":
            level = int(token.tag[1:])  # "h2" -> 2
            inline = tokens[i + 1]
            tracker.update(level, inline.content)
            i += 3
            continue

        # paragraph_open -> inline (content) -> paragraph_close
        if token.type == "paragraph_open":
            inline = tokens[i + 1]
            content = inline.content.strip()
            if content:
                blocks.append(TextBlock(text=content, section_path=tracker.path()))
            i += 3
            continue

        i += 1

    return blocks
