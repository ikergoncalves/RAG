"""Shared types for document parsers.

Every parser turns a source file into an ordered list of ``TextBlock``s. A block
is the smallest unit a parser emits (a PDF page, a paragraph, ...) together with
the citation metadata available for it. Chunking happens later, on top of these
blocks (see ``app.services.chunking``).
"""

from dataclasses import dataclass


@dataclass
class TextBlock:
    """A piece of text extracted from a document with its origin metadata.

    - ``page_number``: 1-based page, when the format exposes pages (PDF). ``None``
      otherwise.
    - ``section_path``: heading breadcrumb, e.g. ``"Chapter 2 > Section 2.1"``.
      ``None`` when the format/position has no heading context.
    """

    text: str
    page_number: int | None = None
    section_path: str | None = None


class SectionPathTracker:
    """Builds a hierarchical heading breadcrumb as headings are encountered.

    Headings are keyed by level (1 = top). Registering a heading at level *L*
    drops any deeper (more nested) levels, so the breadcrumb always reflects the
    current position in the document outline.
    """

    def __init__(self) -> None:
        self._titles: dict[int, str] = {}

    def update(self, level: int, title: str) -> None:
        title = title.strip()
        if not title:
            return
        self._titles[level] = title
        for deeper in [lvl for lvl in self._titles if lvl > level]:
            del self._titles[deeper]

    def path(self) -> str | None:
        if not self._titles:
            return None
        return " > ".join(self._titles[level] for level in sorted(self._titles))
