"""Persistent, citation-preserving library of authorized local source texts."""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any
import unicodedata

from .ingest import ManifestLoadError, SourceManifestEntry, load_manifest


def default_database_path() -> Path:
    configured = os.environ.get("TELUGU_MCP_DATABASE")
    return Path(configured).expanduser() if configured else Path.home() / ".subramanyam" / "library.sqlite3"


def _search_text(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _validate_entry(entry: SourceManifestEntry) -> None:
    if not isinstance(entry.id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", entry.id):
        raise ManifestLoadError("Source IDs must contain only letters, digits, underscores or hyphens")
    for field in ("title", "tradition", "language", "edition", "rights_note"):
        value = getattr(entry, field)
        if not isinstance(value, str) or not value.strip():
            raise ManifestLoadError(f"{entry.id}: {field} must be a nonempty string")
    if entry.rights_basis not in ("public_domain", "permission", "licensed"):
        raise ManifestLoadError(f"{entry.id}: declare rights_basis (public_domain, permission or licensed)")
    if entry.review_status not in ("unreviewed", "reviewed"):
        raise ManifestLoadError(f"{entry.id}: review_status must be unreviewed or reviewed")
    if entry.review_status == "reviewed" and (not isinstance(entry.reviewer, str) or not entry.reviewer.strip()):
        raise ManifestLoadError(f"{entry.id}: reviewed sources require a named reviewer")
    if not entry.local_path or entry.format not in ("text", "txt", "markdown", "md"):
        raise ManifestLoadError(f"{entry.id}: import requires a local UTF-8 text/Markdown file, not a catalogue URL or PDF")
    if entry.chunk_size <= 0:
        raise ManifestLoadError(f"{entry.id}: chunk_size must be positive")


class ScriptureLibrary:
    def __init__(self, database: str | Path):
        self.database = Path(database).expanduser()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError(f"Unsupported library schema version: {version}")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY, metadata TEXT NOT NULL,
                    sha256 TEXT NOT NULL, language TEXT NOT NULL,
                    tradition TEXT NOT NULL, review_status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS passages (
                    passage_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, text TEXT NOT NULL, search_text TEXT NOT NULL,
                    start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
                    start_line INTEGER NOT NULL, end_line INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS passages_source ON passages(source_id, ordinal);
                PRAGMA user_version = 1;
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def import_manifest(self, manifest: str | Path) -> dict[str, int]:
        entries = load_manifest(manifest)
        if not entries:
            raise ManifestLoadError("Import manifest must contain at least one source")
        for entry in entries:
            _validate_entry(entry)
        if len({entry.id for entry in entries}) != len(entries):
            raise ManifestLoadError("Import manifest contains duplicate source IDs")
        passage_count = 0
        with closing(self._connect()) as connection, connection:
            for entry in entries:
                path = entry.resolve_path(Path(manifest).resolve().parent)
                if path is None:
                    raise ManifestLoadError(f"{entry.id}: local_path is required")
                with path.open("r", encoding="utf-8", newline="") as handle:
                    text = handle.read()
                if not text.strip():
                    raise ManifestLoadError(f"{entry.id}: source text is empty")
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                metadata = asdict(entry)
                metadata.pop("local_path")
                metadata["text_characters"] = len(text)
                connection.execute("DELETE FROM sources WHERE source_id = ?", (entry.id,))
                connection.execute(
                    "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?)",
                    (entry.id, json.dumps(metadata, ensure_ascii=False), digest,
                     entry.language, entry.tradition, entry.review_status),
                )
                start = 0
                ordinal = 0
                start_line = 1
                while start < len(text):
                    end = min(start + entry.chunk_size, len(text))
                    if end < len(text):
                        boundary = text.rfind("\n", start, end)
                        if boundary > start:
                            end = boundary + 1
                    passage = text[start:end]
                    end_line = start_line + passage[:-1].count("\n")
                    connection.execute(
                        "INSERT INTO passages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (f"{entry.id}:{digest}:{ordinal}", entry.id, ordinal, passage,
                         _search_text(passage), start, end, start_line, end_line),
                    )
                    passage_count += 1
                    ordinal += 1
                    start_line += passage.count("\n")
                    start = end
        return {"sources_imported": len(entries), "passages_imported": passage_count}

    @staticmethod
    def _payload(row: sqlite3.Row) -> dict[str, Any]:
        metadata = json.loads(row["metadata"])
        prefix = f"{row['source_id']}:{row['sha256']}"
        return {
            "passage_id": row["passage_id"],
            "text": row["text"],
            "previous_passage_id": f"{prefix}:{row['ordinal'] - 1}" if row["ordinal"] else None,
            "next_passage_id": (
                f"{prefix}:{row['ordinal'] + 1}"
                if row["end_char"] < metadata["text_characters"] else None
            ),
            "citation": {
                "source_id": row["source_id"],
                "sha256": row["sha256"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "start_char": row["start_char"],
                "end_char": row["end_char"],
                "source": metadata,
            },
        }

    def sources(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT s.*, COUNT(p.passage_id) AS passage_count FROM sources s "
                "LEFT JOIN passages p USING(source_id) GROUP BY s.source_id ORDER BY s.source_id"
            ).fetchall()
        return [
            {**json.loads(row["metadata"]), "sha256": row["sha256"], "passage_count": row["passage_count"]}
            for row in rows
        ]

    def search(
        self, query: str, *, language: str = "", tradition: str = "",
        source_id: str = "", reviewed_only: bool = True, limit: int = 10, offset: int = 0,
    ) -> dict[str, Any]:
        terms = _search_text(query).split()
        if not terms or len(query) > 500:
            raise ValueError("query must contain 1 to 500 characters of nonblank text")
        if not 1 <= limit <= 50 or offset < 0:
            raise ValueError("limit must be between 1 and 50 and offset must be nonnegative")
        clauses = ["instr(p.search_text, ?) > 0" for _ in terms]
        parameters: list[str | int] = list(terms)
        for column, value in (("s.language", language), ("s.tradition", tradition), ("s.source_id", source_id)):
            if value:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        if reviewed_only:
            clauses.append("s.review_status = 'reviewed'")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT p.*, s.metadata, s.sha256 FROM passages p JOIN sources s USING(source_id) WHERE "
                + " AND ".join(clauses) + " ORDER BY p.source_id, p.ordinal LIMIT ? OFFSET ?",
                (*parameters, limit + 1, offset),
            ).fetchall()
        has_more = len(rows) > limit
        return {
            "results": [self._payload(row) for row in rows[:limit]],
            "next_offset": offset + limit if has_more else None,
            "search_mode": "all_terms_literal_substrings_within_passage",
            "reviewed_only": reviewed_only,
            "status": "matches_found" if rows else "no_matching_passages",
        }

    def passage(self, passage_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT p.*, s.metadata, s.sha256 FROM passages p JOIN sources s USING(source_id) "
                "WHERE passage_id = ?", (passage_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown or outdated passage ID: {passage_id}")
        return self._payload(row)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import authorized local UTF-8 scripture/paddhati texts")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=default_database_path())
    args = parser.parse_args(argv)
    try:
        result = ScriptureLibrary(args.database).import_manifest(args.manifest)
    except (ManifestLoadError, OSError, UnicodeError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
