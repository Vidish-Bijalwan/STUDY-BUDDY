"""RAG-02: structure-aware chunking for study documents.

Splits document text into retrieval chunks of ~300-500 tokens with ~15%
overlap, while respecting document structure:

- headings mark section boundaries and are kept as chunk metadata
- tables become standalone chunks (pipe tables are split row-wise when too
  long, repeating the header so each piece stays interpretable)
- reading order is preserved (two-column layout reuse is ENG-05's job at
  extraction time; here we preserve the order the text arrives in)

Every chunk carries the RAG-02 schema::

    {"doc_id", "page", "section", "char_start", "char_end",
     "text", "embedding_id"}

``char_start``/``char_end`` are offsets into the document's concatenated
text such that ``full_text[char_start:char_end] == chunk["text"]`` always
holds. ``embedding_id`` is a deterministic content hash, so re-chunking the
same document yields stable ids (idempotent indexing).

Pure stdlib, no Flask, no network. Deterministic.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# ---------------------------------------------------------------------------
# Tunables (RAG-02 defaults)
# ---------------------------------------------------------------------------

#: Target chunk size in tokens (~4 chars per token heuristic).
TARGET_TOKENS = 400
#: Chunks are not cut below this size (unless a single block forces it).
MIN_TOKENS = 300
#: Hard cap; a chunk never grows past this.
MAX_TOKENS = 500
#: Fraction of a chunk carried over as overlap into the next chunk.
OVERLAP_RATIO = 0.15

#: Rough chars-per-token heuristic for English prose.
_CHARS_PER_TOKEN = 4

#: Markdown-style headings: "# Title", "## Section", ...
_MD_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
#: Numbered headings: "1 Introduction", "2.3 Methods", "IV. Results"
_NUMBERED_HEADING_RE = re.compile(
    r"^((?:\d+\.)*\d+\.?|[IVXLC]+\.)\s+([A-Z][^\n]{2,110})$"
)
#: A markdown table separator row: "| --- | --- |"
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
#: Sentence splitter for breaking oversized prose blocks.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# 1. Token estimate
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token). Never raises."""
    if not isinstance(text, str) or not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


# ---------------------------------------------------------------------------
# 2. Block classification
# ---------------------------------------------------------------------------

def detect_heading(line: str) -> str | None:
    """Return the cleaned heading text if ``line`` looks like a heading.

    Recognizes Markdown headings ("## Methods"), numbered headings
    ("2.3 Methods"), and short ALL-CAPS lines. Never raises.
    """
    if not isinstance(line, str):
        return None
    stripped = line.strip()
    if not stripped or len(stripped) > 120:
        return None
    m = _MD_HEADING_RE.match(stripped)
    if m:
        return m.group(2).strip() or None
    m = _NUMBERED_HEADING_RE.match(stripped)
    if m:
        return m.group(2).strip() or None
    # ALL-CAPS short line with letters, e.g. "INTRODUCTION".
    if (
        len(stripped) <= 80
        and any(c.isalpha() for c in stripped)
        and stripped == stripped.upper()
        and not _TABLE_SEP_RE.match(stripped)
    ):
        return stripped.title()
    return None


def detect_table_kind(lines: list[str]) -> str | None:
    """Classify a paragraph block as a table, or return None.

    Returns "pipe" for Markdown pipe tables, "tsv" for tab-separated grids.
    Never raises.
    """
    if not isinstance(lines, list):
        return None
    non_empty = [ln for ln in lines if isinstance(ln, str) and ln.strip()]
    if len(non_empty) < 2:
        return None
    pipe_lines = [ln for ln in non_empty if "|" in ln]
    if len(pipe_lines) >= 2 and len(pipe_lines) / len(non_empty) >= 0.5:
        return "pipe"
    tab_lines = [ln for ln in non_empty if "\t" in ln]
    if len(tab_lines) >= 3 and len(tab_lines) / len(non_empty) >= 0.5:
        return "tsv"
    return None


# ---------------------------------------------------------------------------
# 3. Block splitting (page text -> blocks with global char offsets)
# ---------------------------------------------------------------------------

def split_page_blocks(page_text: str, page: int, base_offset: int) -> list[dict]:
    """Split one page's text into blocks.

    A block is ``{"page", "kind", "start", "end", "text"}`` where ``kind``
    is "heading" | "table" | "paragraph", and ``start``/``end`` are offsets
    into the document's concatenated text (``base_offset`` is where this
    page starts). Heading blocks carry the cleaned heading in ``"heading"``
    and table blocks carry ``"table_kind"``. Reading order is preserved.
    Never raises.
    """
    if not isinstance(page_text, str):
        page_text = ""
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    blocks: list[dict] = []
    # Split on blank lines, tracking offsets.
    for m in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]*)*", page_text):
        raw = m.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        start = base_offset + m.start() + (len(raw) - len(raw.lstrip()))
        end = start + len(stripped)
        lines = stripped.split("\n")
        heading = detect_heading(stripped) if len(lines) == 1 else None
        if heading is not None:
            blocks.append({"page": page, "kind": "heading",
                           "start": start, "end": end,
                           "text": stripped, "heading": heading})
            continue
        table_kind = detect_table_kind(lines)
        if table_kind is not None:
            blocks.append({"page": page, "kind": "table",
                           "start": start, "end": end,
                           "text": stripped, "table_kind": table_kind})
            continue
        blocks.append({"page": page, "kind": "paragraph",
                       "start": start, "end": end, "text": stripped})
    return blocks


def _block_tokens(block: dict) -> int:
    return estimate_tokens(block.get("text", ""))


def split_table_rows(block: dict, max_tokens: int = MAX_TOKENS) -> list[dict]:
    """Split an oversized pipe-table block row-wise, repeating the header.

    Returns blocks that each fit in ``max_tokens``; every piece keeps the
    header row (and separator row) so it stays interpretable on its own.
    TSV/unknown tables are returned whole. Never raises.
    """
    try:
        if block.get("table_kind") != "pipe":
            return [block]
        lines = [ln for ln in block["text"].split("\n") if ln.strip()]
        if len(lines) <= 2:
            return [block]
        header = lines[0]
        sep = lines[1] if _TABLE_SEP_RE.match(lines[1]) else None
        body = lines[1:] if not sep else lines[2:]
        if not body:
            return [block]
        prefix = header + ("\n" + sep if sep else "")
        prefix_tokens = estimate_tokens(prefix)
        pieces: list[list[str]] = []
        current: list[str] = []
        cur_tokens = 0
        for row in body:
            row_tokens = estimate_tokens(row)
            if current and cur_tokens + prefix_tokens + row_tokens > max_tokens:
                pieces.append(current)
                current, cur_tokens = [], 0
            current.append(row)
            cur_tokens += row_tokens
        if current:
            pieces.append(current)
        if len(pieces) <= 1:
            return [block]
        out: list[dict] = []
        char = block["start"]
        for rows in pieces:
            text = prefix + "\n" + "\n".join(rows)
            nb = dict(block)
            nb["start"], nb["end"], nb["text"] = char, char + len(text), text
            char += len(text) + 2  # offsets stay monotonic; exactness
            out.append(nb)         # is recomputed by the caller from text
        return out
    except Exception:
        return [block]


def split_long_block(block: dict, max_tokens: int = MAX_TOKENS) -> list[dict]:
    """Split an oversized prose block at sentence boundaries.

    Tables go through :func:`split_table_rows`; headings are returned whole.
    Never raises.
    """
    try:
        if _block_tokens(block) <= max_tokens:
            return [block]
        if block.get("kind") == "table":
            return split_table_rows(block, max_tokens)
        if block.get("kind") == "heading":
            return [block]
        sentences = [s for s in _SENTENCE_SPLIT_RE.split(block["text"])
                     if s.strip()]
        if len(sentences) <= 1:
            return [block]  # one giant sentence: keep whole
        pieces: list[str] = []
        current: list[str] = []
        cur_tokens = 0
        for sent in sentences:
            st = estimate_tokens(sent)
            if current and cur_tokens + st > max_tokens:
                pieces.append(" ".join(current))
                current, cur_tokens = [], 0
            current.append(sent.strip())
            cur_tokens += st
        if current:
            pieces.append(" ".join(current))
        if len(pieces) <= 1:
            return [block]
        return [dict(block, text=p) for p in pieces]
    except Exception:
        return [block]


# ---------------------------------------------------------------------------
# 4. Embedding id (deterministic content hash)
# ---------------------------------------------------------------------------

def make_embedding_id(doc_id: Any, page: int, section: str | None,
                       char_start: int, text: str) -> str:
    """Deterministic embedding id: "emb-" + 16 hex chars of SHA-256.

    Re-chunking identical input yields identical ids (idempotent indexing).
    """
    digest = hashlib.sha256(
        "|".join([str(doc_id), str(page), section or "",
                  str(char_start), text or ""]).encode("utf-8")
    ).hexdigest()
    return "emb-" + digest[:16]


# ---------------------------------------------------------------------------
# 5. Chunk assembly
# ---------------------------------------------------------------------------

def chunk_document(
    doc_id: Any,
    pages: list[Any],
    target_tokens: int = TARGET_TOKENS,
    min_tokens: int = MIN_TOKENS,
    max_tokens: int = MAX_TOKENS,
    overlap_ratio: float = OVERLAP_RATIO,
) -> list[dict]:
    """Chunk a document into structure-aware retrieval chunks.

    ``pages`` is a list of ``{"page": int, "text": str}`` dicts (plain
    strings are accepted too and numbered from 1). Blocks accumulate until
    adding another would exceed ``max_tokens`` while the chunk already holds
    ``>= min_tokens``; tables always start a fresh chunk. After a chunk is
    emitted, trailing whole blocks totaling ~``overlap_ratio`` of the target
    size seed the next chunk (so no sentence is lost at a boundary).

    Returns chunk dicts with ``doc_id, page, section, char_start,
    char_end, text, embedding_id`` plus ``kind`` ("paragraph"|"table"|
    "mixed"). ``page`` is the page where the chunk's new (non-overlap)
    content starts; ``section`` is the most recent heading. Chunks are in
    reading order. Never raises on bad input (yields ``[]``).
    """
    try:
        target_tokens = max(50, int(target_tokens))
        min_tokens = max(1, int(min_tokens))
        max_tokens = max(target_tokens, int(max_tokens))
        overlap_ratio = min(0.5, max(0.0, float(overlap_ratio)))
    except (TypeError, ValueError):
        return []

    norm_pages: list[tuple[int, str]] = []
    if isinstance(pages, (list, tuple)):
        for i, p in enumerate(pages):
            if isinstance(p, dict):
                norm_pages.append((p.get("page", i + 1), p.get("text", "")))
            elif isinstance(p, str):
                norm_pages.append((i + 1, p))
    if not norm_pages:
        return []

    # Concatenated document text; block offsets are global into it.
    full_parts: list[str] = []
    page_offsets: list[int] = []
    for _pg, text in norm_pages:
        page_offsets.append(sum(len(p) + 1 for p in full_parts))
        full_parts.append(text if isinstance(text, str) else "")
    full = "\n".join(full_parts)
    if not full.strip():
        return []

    blocks: list[dict] = []
    for (pg, _text), base in zip(norm_pages, page_offsets, strict=True):
        blocks.extend(split_page_blocks(_text, pg, base))
    # Normalize oversized blocks before assembly.
    flat: list[dict] = []
    for b in blocks:
        flat.extend(split_long_block(b, max_tokens))
    if not flat:
        return []

    overlap_budget = max(1, int(target_tokens * overlap_ratio))
    chunks: list[dict] = []
    current: list[dict] = []   # blocks in the chunk under construction
    cur_tokens = 0
    section: str | None = None

    def flush(is_last: bool = False, carry_overlap: bool = True) -> None:
        nonlocal current, cur_tokens
        if not current:
            return
        # The chunk's section is the section in force when its first
        # non-overlap block starts; overlap blocks inherit their own page
        # but the chunk reports the page of its first block.
        start = current[0]["start"]
        end = current[-1]["end"]
        raw = full[start:end]
        # Strip without breaking the full[char_start:char_end] == text
        # invariant: fold the stripped whitespace back into the offsets.
        lstripped = raw.lstrip()
        rstripped = lstripped.rstrip()
        char_start = start + (len(raw) - len(lstripped))
        char_end = char_start + len(rstripped)
        text = rstripped
        kinds = {b["kind"] for b in current}
        kind = "mixed" if len(kinds) > 1 else next(iter(kinds))
        chunks.append({
            "doc_id": doc_id,
            "page": current[0]["page"],
            "section": current[0].get("_section"),
            "char_start": char_start,
            "char_end": char_end,
            "text": text,
            "embedding_id": make_embedding_id(doc_id, current[0]["page"],
                                              current[0].get("_section"),
                                              char_start, text),
            "kind": kind,
        })
        if is_last or not carry_overlap:
            current = []
            cur_tokens = 0
            return
        # Overlap: carry trailing whole blocks (~overlap_ratio of target).
        carried: list[dict] = []
        carried_tokens = 0
        for b in reversed(current):
            bt = _block_tokens(b)
            if carried and carried_tokens + bt > overlap_budget:
                break
            carried.insert(0, b)
            carried_tokens += bt
        current = carried
        cur_tokens = carried_tokens

    for b in flat:
        if b["kind"] == "heading":
            section = b.get("heading")
            # A heading just before a flush would otherwise be stranded at
            # the end of a chunk; attach it to the next chunk instead.
            if current and cur_tokens >= min_tokens:
                flush()
        b = dict(b)
        b["_section"] = section
        bt = _block_tokens(b)
        if b["kind"] == "table":
            # Tables are standalone chunks: flush any pending prose (without
            # carrying overlap into the table), then flush the table alone
            # (without carrying the table as overlap into what follows).
            flush(carry_overlap=False)
            current.append(b)
            cur_tokens += bt
            flush(carry_overlap=False)
            continue
        if current and cur_tokens >= min_tokens and cur_tokens + bt > max_tokens:
            flush()
        current.append(b)
        cur_tokens += bt
    flush(is_last=True)
    return chunks
