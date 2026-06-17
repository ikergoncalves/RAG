"""Upload and index the demo documents in ``seed-data/`` into a running stack.

This seeds a fresh deployment (for example the public demo) with browsable
content so a visitor sees a working system without uploading anything first.

It follows the same HTTP-only, idempotent pattern as ``index_fixtures.py``:

1. ``GET /documents`` — skip any seed file already present and ``indexed`` (so
   it is safe to re-run without creating duplicates).
2. ``POST /documents`` — upload the remaining files (ingestion runs in the
   background: parse -> chunk -> embed -> index).
3. Poll ``GET /documents/{id}`` until each reaches ``indexed`` (or ``failed``).

Every supported document in ``seed-data/`` is picked up automatically; other
files (such as the PDF generator script) are ignored by extension.

Configure the target with ``RAG_API_BASE_URL`` (default
``http://localhost:8000``), or pass ``--base-url``.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"

# The demo documents live at the repository root, next to backend/ and eval/.
SEED_DIR = Path(__file__).resolve().parents[1] / "seed-data"

# Supported upload types -> MIME type. Files with any other extension (e.g. the
# .py generator) are skipped.
_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html",
    ".htm": "text/html",
}

_TERMINAL_OK = "indexed"
_TERMINAL_FAIL = "failed"


def _base_url(args: argparse.Namespace) -> str:
    return (args.base_url or os.environ.get("RAG_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _seed_files() -> list[Path]:
    """Supported documents in seed-data/, in a stable (sorted) order."""
    return sorted(
        path
        for path in SEED_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in _CONTENT_TYPES
    )


def _existing_indexed(client: httpx.Client, base_url: str) -> set[str]:
    """Return the filenames already present and fully indexed."""
    response = client.get(f"{base_url}/documents", timeout=30.0)
    response.raise_for_status()
    return {doc["filename"] for doc in response.json() if doc.get("status") == _TERMINAL_OK}


def _upload(client: httpx.Client, base_url: str, path: Path) -> str:
    content_type = _CONTENT_TYPES[path.suffix.lower()]
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, content_type)}
        response = client.post(f"{base_url}/documents", files=files, timeout=60.0)
    response.raise_for_status()
    return response.json()["id"]


def _wait_until_indexed(
    client: httpx.Client, base_url: str, document_id: str, timeout: float
) -> str:
    deadline = time.monotonic() + timeout
    status = "pending"
    while time.monotonic() < deadline:
        response = client.get(f"{base_url}/documents/{document_id}", timeout=30.0)
        response.raise_for_status()
        status = response.json()["status"]
        if status in (_TERMINAL_OK, _TERMINAL_FAIL):
            return status
        time.sleep(2.0)
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a stack with the demo documents.")
    parser.add_argument("--base-url", default=None, help="Backend base URL (default %s)." % DEFAULT_BASE_URL)
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Seconds to wait for each document to reach 'indexed' (default 180).",
    )
    args = parser.parse_args()
    base_url = _base_url(args)

    if not SEED_DIR.is_dir():
        print(f"ERROR: seed directory not found: {SEED_DIR}", file=sys.stderr)
        return 1

    seed_files = _seed_files()
    if not seed_files:
        print(f"ERROR: no supported documents found in {SEED_DIR}", file=sys.stderr)
        return 1

    print(f"Seeding {len(seed_files)} document(s) into {base_url} ...")
    with httpx.Client() as client:
        try:
            already = _existing_indexed(client, base_url)
        except httpx.HTTPError as exc:
            print(f"ERROR: could not reach {base_url}/documents: {exc}", file=sys.stderr)
            return 1

        pending: list[tuple[str, str]] = []  # (filename, document_id)
        for path in seed_files:
            if path.name in already:
                print(f"  = {path.name} already indexed; skipping upload")
                continue
            document_id = _upload(client, base_url, path)
            print(f"  + uploaded {path.name} -> {document_id}")
            pending.append((path.name, document_id))

        failures = []
        for filename, document_id in pending:
            status = _wait_until_indexed(client, base_url, document_id, args.timeout)
            marker = "ok" if status == _TERMINAL_OK else "FAILED"
            print(f"  {marker}: {filename} -> {status}")
            if status != _TERMINAL_OK:
                failures.append(filename)

    if failures:
        print(f"ERROR: {len(failures)} document(s) did not index: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("All seed documents indexed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
