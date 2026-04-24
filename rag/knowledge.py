"""
rag/knowledge.py
----------------
Loads business knowledge documents (.md) from knowledge/ and indexes them
into the existing ChromaDB collection alongside lineage graph documents.

Markdown files are split at ## section boundaries — each section becomes
one indexable chunk with kind="knowledge" metadata.
"""

import os

import chromadb

KNOWLEDGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge"
)
MIN_CHUNK_LEN = 60


def _split_md_sections(content: str, source: str) -> list[dict]:
    """Split markdown by ## headings into indexable chunks."""
    chunks = []
    raw_sections = content.split("\n## ")

    for i, section in enumerate(raw_sections):
        if i == 0:
            text = section.strip()
            title = source
        else:
            lines = section.split("\n", 1)
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            text = f"## {title}\n\n{body}"

        if len(text) < MIN_CHUNK_LEN:
            continue

        chunks.append(
            {
                "text": text,
                "metadata": {
                    "kind": "knowledge",
                    "source": source,
                    "name": title,
                    "namespace": "",
                },
            }
        )
    return chunks


def load_knowledge_chunks(knowledge_dir: str = KNOWLEDGE_DIR) -> list[dict]:
    """Load all .md files from knowledge_dir and return chunks ready for indexing."""
    if not os.path.isdir(knowledge_dir):
        return []

    chunks = []
    for fname in sorted(os.listdir(knowledge_dir)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(knowledge_dir, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        chunks.extend(_split_md_sections(content, fname))

    return chunks


def index_knowledge(
    collection: chromadb.Collection, knowledge_dir: str = KNOWLEDGE_DIR
) -> int:
    """Upsert all knowledge chunks into the collection. Returns the number added."""
    chunks = load_knowledge_chunks(knowledge_dir)
    if not chunks:
        return 0

    docs = [c["text"] for c in chunks]
    ids = [f"knowledge::{c['metadata']['source']}::{i}" for i, c in enumerate(chunks)]
    metas = [c["metadata"] for c in chunks]

    collection.upsert(documents=docs, ids=ids, metadatas=metas)
    return len(chunks)
