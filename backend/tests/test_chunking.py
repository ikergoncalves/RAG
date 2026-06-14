"""Chunking tests: character offsets, token sizes, overlap, metadata.

The key invariant is that ``document_text[char_start:char_end] == content`` for
every chunk, which is what lets the frontend highlight a cited quote inside the
original text.
"""

from pathlib import Path

import tiktoken

from app.core.config import settings
from app.services.chunking import assemble_document_text, chunk_blocks
from app.services.parsing import parse_document
from app.services.parsing.base import TextBlock

FIXTURES = Path(__file__).parent / "fixtures"

CHUNK_SIZE = 100
OVERLAP = 20


def _long_text(word_count: int) -> str:
    """Deterministic ASCII text so token boundaries map cleanly to characters."""
    return " ".join(f"word{i:04d}" for i in range(word_count))


def test_char_offsets_match_assembled_text() -> None:
    blocks = [
        TextBlock(text=_long_text(600), page_number=1, section_path="A > B"),
        TextBlock(text=_long_text(60), page_number=2, section_path="C"),
    ]
    document_text, _ = assemble_document_text(blocks)

    chunks = chunk_blocks(blocks, chunk_size=CHUNK_SIZE, overlap=OVERLAP)

    assert chunks
    for chunk in chunks:
        assert document_text[chunk.char_start : chunk.char_end] == chunk.content


def test_chunk_sizes_and_overlap_are_consistent() -> None:
    block = TextBlock(text=_long_text(800), page_number=3, section_path="X > Y")
    document_text, _ = assemble_document_text([block])
    encoder = tiktoken.get_encoding(settings.tiktoken_encoding)

    chunks = chunk_blocks([block], chunk_size=CHUNK_SIZE, overlap=OVERLAP)

    assert len(chunks) >= 2
    # Source metadata is inherited by every chunk.
    for chunk in chunks:
        assert chunk.token_count <= CHUNK_SIZE
        assert chunk.page_number == 3
        assert chunk.section_path == "X > Y"
    # Every chunk except the last fills the window.
    for chunk in chunks[:-1]:
        assert chunk.token_count == CHUNK_SIZE

    # Consecutive chunks overlap by ~OVERLAP tokens and always move forward.
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert prev.char_start < nxt.char_start < prev.char_end
        overlap_text = document_text[nxt.char_start : prev.char_end]
        overlap_tokens = len(encoder.encode(overlap_text))
        assert OVERLAP - 10 <= overlap_tokens <= OVERLAP + 10


def test_chunk_index_is_sequential_across_blocks() -> None:
    blocks = [TextBlock(text=_long_text(300)), TextBlock(text=_long_text(300))]

    chunks = chunk_blocks(blocks, chunk_size=CHUNK_SIZE, overlap=OVERLAP)

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunking_preserves_section_path_from_markdown() -> None:
    blocks = parse_document(FIXTURES / "sample.md")

    chunks = chunk_blocks(blocks)

    cited = [chunk for chunk in chunks if "MarkdownSection21" in chunk.content]
    assert cited
    assert all(chunk.section_path == "Chapter 2 > Section 2.1" for chunk in cited)
