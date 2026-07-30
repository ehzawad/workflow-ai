"""Small deterministic helpers shared by the application."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from workflow_ai.exceptions import PathSafetyError

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[\w-]+", flags=re.UNICODE)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def canonical_json(value: Any) -> str:
    """Serialize a value into stable JSON suitable for hashing and audit records."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_text(value: str) -> str:
    """Return the hexadecimal SHA-256 digest of UTF-8 text."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slugify(value: str, *, fallback: str = "untitled", max_length: int = 80) -> str:
    """Convert arbitrary text to a stable, filesystem-safe ASCII slug."""

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_RE.sub("-", normalized.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or fallback


def deduplicate(values: Iterable[str]) -> list[str]:
    """Deduplicate strings case-insensitively while retaining input order."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def safe_child(root: Path, relative: str | Path) -> Path:
    """Resolve a path below *root* and reject absolute or traversal paths."""

    root_resolved = root.expanduser().resolve()
    candidate = Path(relative)
    if candidate.is_absolute():
        raise PathSafetyError(f"Absolute child path is not allowed: {candidate}")
    resolved = (root_resolved / candidate).resolve()
    if not resolved.is_relative_to(root_resolved):
        raise PathSafetyError(f"Path escapes configured root: {candidate}")
    return resolved


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace a UTF-8 text file in the same filesystem."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def fts_query(value: str, *, operator: Literal["AND", "OR"] = "AND") -> str:
    """Turn free text into a quoted SQLite FTS5 query.

    ``AND`` is the precise first-pass retrieval mode. ``OR`` is used as a
    controlled recall fallback when a natural-language question contains words
    that do not all occur in the same note.
    """

    tokens = [token.replace('"', '""') for token in _TOKEN_RE.findall(value)]
    if not tokens:
        return ""
    return f" {operator} ".join(f'"{token}"' for token in tokens[:20])
