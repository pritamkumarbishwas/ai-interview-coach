"""Parse `data/knowledge_base/` (markdown + JSON) into embeddable chunks.

Layout: each subdirectory is a Qdrant collection, e.g.
`technical_concepts/indexing.md` → collection `technical_concepts`.

Markdown files may carry front matter (`topic`, `roles`) and are split on
headings/paragraphs into chunks of at most MAX_CHUNK_CHARS. JSON files hold
explicit entries ({"text": ..., "topic": ..., "roles": [...], "collection":
...}); `collection` may also come from the file's directory.
"""

import json
import re
import uuid
from pathlib import Path

from app.schemas.rag import KnowledgeChunk
from app.services.rag_service import COLLECTIONS

MAX_CHUNK_CHARS = 1_200

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"(?m)^(#{1,6}\s+.*)$")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def _chunk_id(source: str, index: int) -> str:
    """Stable UUID so re-ingestion overwrites instead of duplicating."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"knowledge:{source}:{index}"))


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip().lower()] = value.strip()
    return meta, text[match.end() :]


def _parse_roles(meta: dict[str, str]) -> list[str]:
    raw = meta.get("roles", "")
    roles = [part.strip() for part in raw.split(",") if part.strip()]
    return roles or ["*"]


def _pack_paragraphs(body: str, max_chars: int) -> list[str]:
    """Greedy paragraph packing; a single huge paragraph is sliced hard."""
    chunks: list[str] = []
    current = ""
    for paragraph in _PARAGRAPH_RE.split(body):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(paragraph) > max_chars:
            chunks.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def parse_markdown(text: str, source: str) -> dict[str, list[KnowledgeChunk]]:
    """One markdown file → `{collection: chunks}` (collection from the dir)."""
    meta, body = _parse_front_matter(text)
    if not body.strip():
        return {}
    collection = meta.get("collection") or _collection_for_source(source)
    if collection not in COLLECTIONS:
        raise ValueError(
            f"{source}: {collection!r} is not a collection "
            f"(expected a directory like technical_concepts/ or 'collection:' front matter)"
        )

    topic = meta.get("topic", "*") or "*"
    roles = _parse_roles(meta)

    # Split on headings so each chunk carries its section heading as context.
    parts = _HEADING_RE.split(body)
    sections: list[str] = []
    if parts[0].strip():
        sections.append(parts[0])
    # re.split with one capture group yields [pre, heading, text, ...] (odd
    # length), so heading/text always come in pairs after the first item.
    sections += [f"{parts[i].strip()}\n\n{parts[i + 1]}" for i in range(1, len(parts), 2)]

    chunks: list[KnowledgeChunk] = []
    index = 0
    for section in sections:
        for chunk_text in _pack_paragraphs(section, MAX_CHUNK_CHARS):
            chunks.append(
                KnowledgeChunk(
                    id=_chunk_id(source, index),
                    text=chunk_text,
                    topic=topic,
                    roles=roles,
                    source=source,
                )
            )
            index += 1
    return {collection: chunks} if chunks else {}


def parse_json(text: str, source: str) -> dict[str, list[KnowledgeChunk]]:
    """JSON entries (list or {"chunks": [...]}) → `{collection: chunks}`."""
    data = json.loads(text)
    if isinstance(data, dict):
        entries = data.get("chunks")
        if not isinstance(entries, list):
            raise ValueError(f"{source}: expected a list or an object with a 'chunks' list")
    elif isinstance(data, list):
        entries = data
    else:
        raise ValueError(f"{source}: top-level JSON must be a list or object")

    default_collection = _collection_for_source(source)
    grouped: dict[str, list[KnowledgeChunk]] = {}
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict) or not str(entry.get("text", "")).strip():
            raise ValueError(f"{source}: entry #{position} needs a non-empty 'text'")
        collection = str(entry.get("collection") or default_collection)
        if collection not in COLLECTIONS:
            raise ValueError(f"{source}: entry #{position} has unknown collection {collection!r}")
        roles = entry.get("roles") or ["*"]
        chunk = KnowledgeChunk(
            id=_chunk_id(source, position),
            text=str(entry["text"]).strip(),
            topic=str(entry.get("topic", "*") or "*"),
            roles=[str(role) for role in roles],
            source=source,
        )
        grouped.setdefault(collection, []).append(chunk)
    return grouped


def _collection_for_source(source: str) -> str:
    """Collection from the source's parent directory ('' for root-level files)."""
    parts = Path(source).parts
    return parts[0] if len(parts) > 1 else ""


def load_knowledge_base(root: Path) -> dict[str, list[KnowledgeChunk]]:
    """Recursively load every .md/.json file under `root`, grouped by collection."""
    if not root.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {root}")
    grouped: dict[str, list[KnowledgeChunk]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        if suffix not in (".md", ".json"):
            continue
        source = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        parsed = parse_markdown(text, source) if suffix == ".md" else parse_json(text, source)
        for collection, chunks in parsed.items():
            grouped.setdefault(collection, []).extend(chunks)
    return grouped
