"""Local SQLite FTS5 index over the Markdown vault."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from workflow_ai.models import SearchHit
from workflow_ai.utils import fts_query
from workflow_ai.vault.frontmatter import load_markdown


class VaultIndex:
    def __init__(self, *, database_path: Path, vault_root: Path) -> None:
        self.database_path = database_path
        self.vault_root = vault_root.resolve()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    path UNINDEXED,
                    title,
                    body,
                    tags,
                    projects,
                    tokenize = 'porter unicode61'
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def rebuild(self) -> int:
        self.initialize()
        count = 0
        with self._connect() as connection:
            connection.execute("DELETE FROM notes_fts")
            for path in sorted(self.vault_root.rglob("*.md")):
                record = self._read_record(path)
                if record is None:
                    continue
                connection.execute(
                    "INSERT INTO notes_fts(path, title, body, tags, projects) VALUES (?, ?, ?, ?, ?)",
                    record,
                )
                count += 1
        return count

    def upsert(self, path: Path) -> None:
        self.initialize()
        record = self._read_record(path)
        if record is None:
            return
        relative = path.resolve().relative_to(self.vault_root).as_posix()
        with self._connect() as connection:
            connection.execute("DELETE FROM notes_fts WHERE path = ?", (relative,))
            connection.execute(
                "INSERT INTO notes_fts(path, title, body, tags, projects) VALUES (?, ?, ?, ?, ?)",
                record,
            )

    def search(self, query: str, *, limit: int = 10) -> list[SearchHit]:
        precise_query = fts_query(query)
        if not precise_query:
            return []
        limit = max(1, min(limit, 100))
        self.initialize()
        with self._connect() as connection:
            rows = self._search_rows(connection, query=precise_query, limit=limit)
            if not rows:
                recall_query = fts_query(query, operator="OR")
                if recall_query != precise_query:
                    rows = self._search_rows(connection, query=recall_query, limit=limit)
        return [
            SearchHit(
                path=row["path"],
                title=row["title"],
                snippet=row["snippet"] or "",
                score=round(-float(row["rank"]), 6),
                tags=_split_storage(row["tags"]),
                projects=_split_storage(row["projects"]),
            )
            for row in rows
        ]

    @staticmethod
    def _search_rows(
        connection: sqlite3.Connection,
        *,
        query: str,
        limit: int,
    ) -> list[sqlite3.Row]:
        return connection.execute(
            """
            SELECT path, title,
                   snippet(notes_fts, 2, '<mark>', '</mark>', ' … ', 24) AS snippet,
                   bm25(notes_fts, 2.0, 6.0, 1.0, 1.5, 1.5) AS rank,
                   tags, projects
            FROM notes_fts
            WHERE notes_fts MATCH ?
            ORDER BY rank ASC
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()

    def _read_record(self, path: Path) -> tuple[str, str, str, str, str] | None:
        try:
            text = path.read_text(encoding="utf-8")
            metadata, body = load_markdown(text)
        except (OSError, UnicodeError, ValueError):
            return None
        relative = path.resolve().relative_to(self.vault_root).as_posix()
        title = str(metadata.get("title") or _first_heading(body) or path.stem)
        tags = _join_storage(metadata.get("tags"))
        projects = _join_storage(metadata.get("projects"))
        return relative, title, body, tags, projects


def _first_heading(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _join_storage(value: object) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, str):
        return value
    return ""


def _split_storage(value: str | None) -> list[str]:
    return [item for item in (value or "").splitlines() if item]
