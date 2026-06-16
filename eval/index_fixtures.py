"""Upload and index the test fixtures into a running stack.

The evaluation dataset (``dataset.json``) is grounded in the fixtures under
``backend/tests/fixtures/`` (``sample.md``, ``sample.pdf``, ``sample.docx``,
``sample.html``). Before running ``run_ragas.py`` those documents must be
ingested and indexed so the chat pipeline can retrieve them.

This script talks to the backend over HTTP only (no backend imports):

1. ``GET /documents`` — skip any fixture already present and ``indexed`` (so it
   is safe to re-run without creating duplicate documents).
2. ``POST /documents`` — upload the remaining fixtures (ingestion runs in the
   background: parse -> chunk -> embed -> index).
3. Poll ``GET /documents/{id}`` until each reaches ``indexed`` (or ``failed``).

Configure the target with ``RAG_API_BASE_URL`` (default
``http://localhost:8000``).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"

# The fixtures the evaluation dataset is written against, in a stable order.
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures"
FIXTURE_FILES = ["sample.md", "sample.pdf", "sample.docx", "sample.html"]

_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html",
}

_TERMINAL_OK = "indexed"
_TERMINAL_FAIL = "failed"


def _base_url(args: argparse.Namespace) -> str:
    import os

    return (args.base_url or os.environ.get("RAG_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _existing_indexed(client: httpx.Client, base_url: str) -> set[str]:
    """Return the filenames already present and fully indexed."""
    response = client.get(f"{base_url}/documents", timeout=30.0)
    response.raise_for_status()
    return {
        doc["filename"]
        for doc in response.json()
        if doc.get("status") == _TERMINAL_OK
    }


def _upload(client: httpx.Client, base_url: str, path: Path) -> str:
    content_type = _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
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
    parser = argparse.ArgumentParser(description="Index the eval fixtures into a running stack.")
    parser.add_argument("--base-url", default=None, help="Backend base URL (default %s)." % DEFAULT_BASE_URL)
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Seconds to wait for each document to reach 'indexed' (default 180).",
    )
    args = parser.parse_args()
    base_url = _base_url(args)

    print(f"Indexing fixtures into {base_url} ...")
    with httpx.Client() as client:
        try:
            already = _existing_indexed(client, base_url)
        except httpx.HTTPError as exc:
            print(f"ERROR: could not reach {base_url}/documents: {exc}", file=sys.stderr)
            return 1

        pending: list[tuple[str, str]] = []  # (filename, document_id)
        for filename in FIXTURE_FILES:
            path = FIXTURE_DIR / filename
            if not path.exists():
                print(f"  ! missing fixture {path}", file=sys.stderr)
                return 1
            if filename in already:
                print(f"  = {filename} already indexed; skipping upload")
                continue
            document_id = _upload(client, base_url, path)
            print(f"  + uploaded {filename} -> {document_id}")
            pending.append((filename, document_id))

        failures = []
        for filename, document_id in pending:
            status = _wait_until_indexed(client, base_url, document_id, args.timeout)
            marker = "ok" if status == _TERMINAL_OK else "FAILED"
            print(f"  {marker}: {filename} -> {status}")
            if status != _TERMINAL_OK:
                failures.append(filename)

    if failures:
        print(f"ERROR: {len(failures)} fixture(s) did not index: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("All fixtures indexed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
