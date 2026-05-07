"""
rag/knowledge.py
----------------
Loads business knowledge documents (.md) from knowledge/ and indexes them
into the existing ChromaDB collection alongside lineage graph documents.

Markdown files are split at ## section boundaries — each section becomes
one or more indexable chunks with kind="knowledge" metadata.

Large sections are further split:
- Markdown tables → every TABLE_ROWS_PER_CHUNK rows, header repeated in each chunk
- Plain text → at paragraph (\\n\\n) boundaries up to MAX_CHUNK_LEN chars
"""

import os
import re

import chromadb

KNOWLEDGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge"
)
MIN_CHUNK_LEN = 60
MAX_CHUNK_LEN = 1500
TABLE_ROWS_PER_CHUNK = 15


def _make_chunk(text: str, name: str, source: str) -> dict:
    return {
        "text": f"[{source}]\n{text}",
        "metadata": {"kind": "knowledge", "source": source, "name": name, "namespace": ""},
    }


def _split_table_section(header: str, rows: list[str], title: str, source: str) -> list[dict]:
    """Split a large markdown table into chunks, repeating the header in each."""
    chunks = []
    for i in range(0, len(rows), TABLE_ROWS_PER_CHUNK):
        batch = rows[i : i + TABLE_ROWS_PER_CHUNK]
        text = f"## {title}\n{header}\n" + "\n".join(batch)
        name = f"{title} (filas {i + 1}-{i + len(batch)})"
        chunks.append(_make_chunk(text, name, source))
    return chunks


def _split_long_section(title: str, text: str, source: str) -> list[dict]:
    """Split a section that exceeds MAX_CHUNK_LEN into sub-chunks."""
    lines = text.split("\n")

    # Detect markdown table: look for a separator row like |---|---|
    sep_indices = [i for i, l in enumerate(lines) if re.match(r"^\|[-| :]+\|", l)]
    if sep_indices:
        sep_idx = sep_indices[0]
        header = "\n".join(lines[: sep_idx + 1])
        data_rows = [l for l in lines[sep_idx + 1 :] if l.strip()]
        if data_rows:
            return _split_table_section(header, data_rows, title, source)

    # Non-table: split at paragraph boundaries
    chunks: list[dict] = []
    current = ""
    part = 1
    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}" if current else para
        if current and len(candidate) > MAX_CHUNK_LEN:
            chunks.append(_make_chunk(current.strip(), f"{title} ({part})", source))
            part += 1
            current = para
        else:
            current = candidate
    if current.strip():
        name = f"{title} ({part})" if part > 1 else title
        chunks.append(_make_chunk(current.strip(), name, source))
    return chunks


def _split_md_sections(content: str, source: str) -> list[dict]:
    """Split markdown by ## headings into indexable chunks."""
    chunks: list[dict] = []
    raw_sections = content.split("\n## ")

    for i, section in enumerate(raw_sections):
        if i == 0:
            text = section.strip()
            # Use # Title from first line if present; fall back to filename
            first_line = text.split("\n", 1)[0].strip()
            title = first_line[2:].strip() if first_line.startswith("# ") else source
        else:
            lines = section.split("\n", 1)
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            text = f"## {title}\n\n{body}"

        if len(text) < MIN_CHUNK_LEN:
            continue

        if len(text) <= MAX_CHUNK_LEN:
            chunks.append(_make_chunk(text, title, source))
        else:
            chunks.extend(_split_long_section(title, text, source))

    return chunks


def load_knowledge_chunks(knowledge_dir: str = KNOWLEDGE_DIR) -> list[dict]:
    """Load all .md files from knowledge_dir and return chunks ready for indexing."""
    if not os.path.isdir(knowledge_dir):
        return []

    chunks = []
    for root, _, files in os.walk(knowledge_dir):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            path = os.path.join(root, fname)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            # Use relative path from knowledge_dir as source for clarity
            rel = os.path.relpath(path, knowledge_dir)
            chunks.extend(_split_md_sections(content, rel))

    return chunks


def index_knowledge(
    collection: chromadb.Collection, knowledge_dir: str = KNOWLEDGE_DIR
) -> int:
    """Upsert all knowledge chunks into the collection. Returns the number added."""
    chunks = load_knowledge_chunks(knowledge_dir)
    if not chunks:
        return 0

    # E5 model requires "passage: " prefix for stored documents (same as lineage docs)
    docs = [f"passage: {c['text']}" for c in chunks]
    ids = [f"knowledge::{c['metadata']['source']}::{i}" for i, c in enumerate(chunks)]
    metas = [c["metadata"] for c in chunks]

    collection.upsert(documents=docs, ids=ids, metadatas=metas)
    return len(chunks)
