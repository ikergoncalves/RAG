"""Local filesystem storage for uploaded source files.

Files are stored as ``<upload_dir>/<document_id><ext>`` so the path can be
reconstructed from the document id and its original filename.
"""

import uuid
from pathlib import Path

from app.core.config import settings


def _base_dir() -> Path:
    base = Path(settings.upload_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base


def storage_path(document_id: uuid.UUID, filename: str) -> Path:
    """Deterministic on-disk path for a document's source file."""
    extension = Path(filename).suffix.lower()
    return _base_dir() / f"{document_id}{extension}"


def save_upload(document_id: uuid.UUID, filename: str, data: bytes) -> Path:
    path = storage_path(document_id, filename)
    path.write_bytes(data)
    return path
