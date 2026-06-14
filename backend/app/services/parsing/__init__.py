"""Document parsing package.

``parse_document`` dispatches a source file to the right parser based on its
filename extension (falling back to the declared content type) and returns an
ordered list of :class:`~app.services.parsing.base.TextBlock`.
"""

from pathlib import Path

from app.services.parsing import (
    docx_parser,
    html_parser,
    markdown_parser,
    pdf_parser,
)
from app.services.parsing.base import SectionPathTracker, TextBlock

_EXTENSION_PARSERS = {
    ".pdf": pdf_parser.parse,
    ".docx": docx_parser.parse,
    ".md": markdown_parser.parse,
    ".markdown": markdown_parser.parse,
    ".html": html_parser.parse,
    ".htm": html_parser.parse,
}

# Best-effort mapping from MIME type to extension, used when the filename has no
# (recognized) extension.
_CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/markdown": ".md",
    "text/x-markdown": ".md",
    "text/html": ".html",
}

SUPPORTED_EXTENSIONS = frozenset(_EXTENSION_PARSERS)


class UnsupportedDocumentError(ValueError):
    """Raised when no parser matches the given filename/content type."""


def resolve_extension(filename: str, content_type: str | None = None) -> str:
    """Return the supported extension for a file, or raise ``UnsupportedDocumentError``."""
    extension = Path(filename).suffix.lower()
    if extension in _EXTENSION_PARSERS:
        return extension
    if content_type and content_type in _CONTENT_TYPE_EXTENSIONS:
        return _CONTENT_TYPE_EXTENSIONS[content_type]
    raise UnsupportedDocumentError(
        f"Unsupported document type (filename={filename!r}, content_type={content_type!r}). "
        f"Supported extensions: {sorted(SUPPORTED_EXTENSIONS)}"
    )


def parse_document(
    path: str | Path,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> list[TextBlock]:
    """Parse a document file into text blocks with origin metadata."""
    extension = resolve_extension(filename or str(path), content_type)
    return _EXTENSION_PARSERS[extension](path)


__all__ = [
    "SectionPathTracker",
    "SUPPORTED_EXTENSIONS",
    "TextBlock",
    "UnsupportedDocumentError",
    "parse_document",
    "resolve_extension",
]
