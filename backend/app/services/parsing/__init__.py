"""Document parsing package.

``parse_document`` dispatches a source file to the right parser based on its
filename extension (falling back to the declared content type) and returns an
ordered list of :class:`~app.services.parsing.base.TextBlock`.
"""

import importlib
from collections.abc import Callable
from pathlib import Path

from app.services.parsing.base import SectionPathTracker, TextBlock

# Extension -> the parser submodule whose ``parse(path)`` handles it. The parser
# modules are imported lazily (see ``_load_parser``) so their parsing libraries
# (pypdf, python-docx + lxml, beautifulsoup4, markdown-it-py) never load at
# import time — only when a document is actually parsed. This keeps the startup
# memory footprint small, which matters on RAM-limited hosts.
_EXTENSION_MODULES = {
    ".pdf": "pdf_parser",
    ".docx": "docx_parser",
    ".md": "markdown_parser",
    ".markdown": "markdown_parser",
    ".html": "html_parser",
    ".htm": "html_parser",
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

SUPPORTED_EXTENSIONS = frozenset(_EXTENSION_MODULES)


class UnsupportedDocumentError(ValueError):
    """Raised when no parser matches the given filename/content type."""


def resolve_extension(filename: str, content_type: str | None = None) -> str:
    """Return the supported extension for a file, or raise ``UnsupportedDocumentError``."""
    extension = Path(filename).suffix.lower()
    if extension in _EXTENSION_MODULES:
        return extension
    if content_type and content_type in _CONTENT_TYPE_EXTENSIONS:
        return _CONTENT_TYPE_EXTENSIONS[content_type]
    raise UnsupportedDocumentError(
        f"Unsupported document type (filename={filename!r}, content_type={content_type!r}). "
        f"Supported extensions: {sorted(SUPPORTED_EXTENSIONS)}"
    )


def _load_parser(extension: str) -> Callable[[str | Path], list[TextBlock]]:
    """Import the parser submodule for ``extension`` lazily and return its ``parse``."""
    module = importlib.import_module(f"app.services.parsing.{_EXTENSION_MODULES[extension]}")
    return module.parse


def parse_document(
    path: str | Path,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> list[TextBlock]:
    """Parse a document file into text blocks with origin metadata."""
    extension = resolve_extension(filename or str(path), content_type)
    return _load_parser(extension)(path)


__all__ = [
    "SectionPathTracker",
    "SUPPORTED_EXTENSIONS",
    "TextBlock",
    "UnsupportedDocumentError",
    "parse_document",
    "resolve_extension",
]
