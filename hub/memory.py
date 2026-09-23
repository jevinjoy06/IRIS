import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Tier = Literal["core", "relevant", "archive"]

_DB_PATH: Path | None = None


def _db_path() -> Path:
    if _DB_PATH is not None:
        return _DB_PATH
    import os
    return Path(__file__).parent / os.environ.get("DB_PATH", "iris.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tier         TEXT    NOT NULL CHECK(tier IN ('core','relevant','archive')),
                content      TEXT    NOT NULL,
                importance   REAL    NOT NULL DEFAULT 0.5,
                tags         TEXT    NOT NULL DEFAULT '[]',
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT,
                created_at   TEXT    NOT NULL
            )
        """)


def write_fact(
    content: str,
    tier: Tier = "relevant",
    importance: float = 0.5,
    tags: list[str] | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(tags or [])
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO facts (tier, content, importance, tags, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (tier, content, importance, tags_json, now),
        )
        return cur.lastrowid


def get_core_facts() -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content FROM facts WHERE tier = 'core' ORDER BY importance DESC"
        ).fetchall()
    if rows:
        _bump_access([r["id"] for r in rows])
    return [r["content"] for r in rows]


def search_facts(query: str, limit: int = 10) -> list[str]:
    """Keyword search across non-archived facts."""
    terms = query.lower().split()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content FROM facts WHERE tier != 'archive'"
        ).fetchall()

    scored = []
    for row in rows:
        text = row["content"].lower()
        hits = sum(1 for t in terms if t in text)
        if hits:
            scored.append((hits, row["id"], row["content"]))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]
    if top:
        _bump_access([r[1] for r in top])
    return [r[2] for r in top]


def _bump_access(ids: list[int]) -> None:
    if not ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" * len(ids))
    with _connect() as conn:
        conn.execute(
            f"""UPDATE facts
                SET access_count = access_count + 1, last_accessed = ?
                WHERE id IN ({placeholders})""",
            [now, *ids],
        )


def build_memory_context(query: str) -> str:
    core = get_core_facts()
    relevant = search_facts(query, limit=10)
    # Deduplicate: relevant may overlap with core
    core_set = set(core)
    relevant = [f for f in relevant if f not in core_set]

    parts: list[str] = []
    if core:
        parts.append("## Core facts\n" + "\n".join(f"- {f}" for f in core))
    if relevant:
        parts.append("## Relevant facts\n" + "\n".join(f"- {f}" for f in relevant))
    return "\n\n".join(parts)
