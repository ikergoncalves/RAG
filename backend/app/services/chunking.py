"""Token-based chunking with character offsets and overlap.

Blocks produced by the parsers are assembled into a single document text, and
each block is split into overlapping, token-bounded chunks. Every chunk keeps:

- ``page_number`` / ``section_path`` inherited from its source block,
- ``char_start`` / ``char_end`` offsets into the assembled document text, such
  that ``document_text[char_start:char_end] == content`` (needed so the frontend
  can highlight a cited quote inside the original text).

The encoder (``tiktoken``) is loaded lazily and cached, so importing this module
never triggers a network download.
"""

from dataclasses import dataclass

import tiktoken

from app.core.config import settings
from app.services.parsing.base import TextBlock

# Separator inserted between blocks when assembling the document text. Chunk
# content never spans this separator, so it does not affect offset correctness.
_BLOCK_SEPARATOR = "\n\n"

_encoders: dict[str, "tiktoken.Encoding"] = {}


def _get_encoder(name: str) -> "tiktoken.Encoding":
    if name not in _encoders:
        _encoders[name] = tiktoken.get_encoding(name)
    return _encoders[name]


@dataclass
class ChunkData:
    """A chunk ready to be persisted, with citation metadata and offsets."""

    chunk_index: int
    content: str
    token_count: int
    page_number: int | None
    section_path: str | None
    char_start: int
    char_end: int


def _clean_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    """Drop blocks that are empty after stripping (keeps offsets meaningful)."""
    cleaned = []
    for block in blocks:
        text = block.text.strip()
        if text:
            cleaned.append(
                TextBlock(
                    text=text,
                    page_number=block.page_number,
                    section_path=block.section_path,
                )
            )
    return cleaned


def assemble_document_text(blocks: list[TextBlock]) -> tuple[str, list[tuple[int, int]]]:
    """Join blocks into one text and return it plus each block's (start, end) span."""
    blocks = _clean_blocks(blocks)
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    cursor = 0
    for index, block in enumerate(blocks):
        if index > 0:
            cursor += len(_BLOCK_SEPARATOR)
        start = cursor
        end = start + len(block.text)
        spans.append((start, end))
        parts.append(block.text)
        cursor = end
    return _BLOCK_SEPARATOR.join(parts), spans


def chunk_blocks(
    blocks: list[TextBlock],
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
    encoding_name: str | None = None,
) -> list[ChunkData]:
    """Split blocks into overlapping token-bounded chunks.

    ``chunk_size`` and ``overlap`` are in tokens and default to the configured
    values. Chunks are produced per block (a chunk never spans two blocks, so it
    keeps a single page/section), and ``chunk_index`` is assigned sequentially
    across the whole document.
    """
    chunk_size = chunk_size or settings.chunk_size_tokens
    overlap = overlap if overlap is not None else settings.chunk_overlap_tokens
    encoding_name = encoding_name or settings.tiktoken_encoding

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be >= 0 and smaller than chunk_size")

    encoder = _get_encoder(encoding_name)
    cleaned = _clean_blocks(blocks)
    _, spans = assemble_document_text(cleaned)
    step = chunk_size - overlap

    chunks: list[ChunkData] = []
    index = 0
    for block, (block_start, _block_end) in zip(cleaned, spans, strict=False):
        tokens = encoder.encode(block.text)
        if not tokens:
            continue

        start_token = 0
        total = len(tokens)
        while start_token < total:
            end_token = min(start_token + chunk_size, total)
            local_start = len(encoder.decode(tokens[:start_token]))
            local_end = len(encoder.decode(tokens[:end_token]))
            chunks.append(
                ChunkData(
                    chunk_index=index,
                    content=block.text[local_start:local_end],
                    token_count=end_token - start_token,
                    page_number=block.page_number,
                    section_path=block.section_path,
                    char_start=block_start + local_start,
                    char_end=block_start + local_end,
                )
            )
            index += 1
            if end_token == total:
                break
            start_token += step

    return chunks
