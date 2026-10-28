import json
import sqlite3
import uuid
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                role        TEXT    NOT NULL CHECK(role IN ('user','assistant','tool')),
                content     TEXT    NOT NULL,
                tool_name   TEXT,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id      TEXT    PRIMARY KEY,
                label           TEXT,
                status          TEXT    NOT NULL DEFAULT 'open' CHECK(status IN ('open','warm','closed')),
                summary         TEXT,
                created_at      TEXT    NOT NULL,
                last_active_at  TEXT    NOT NULL
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
        # Dedup: an existing non-archived fact with the same content (case-insensitive)
        # gets its importance/tier bumped instead of being duplicated.
        existing = conn.execute(
            "SELECT id, importance FROM facts WHERE tier != 'archive' AND lower(content) = lower(?)",
            (content,),
        ).fetchone()
        if existing:
            new_importance = max(existing["importance"], importance)
            conn.execute(
                "UPDATE facts SET importance = ?, tier = ?, last_accessed = ? WHERE id = ?",
                (new_importance, tier, now, existing["id"]),
            )
            return existing["id"]

        cur = conn.execute(
            """INSERT INTO facts (tier, content, importance, tags, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (tier, content, importance, tags_json, now),
        )
        return cur.lastrowid


def get_core_facts(limit: int = 20) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content FROM facts WHERE tier = 'core' ORDER BY importance DESC, created_at DESC LIMIT ?",
            (limit,),
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
    core_set = set(core)
    relevant = [f for f in relevant if f not in core_set]

    parts: list[str] = []
    if core:
        parts.append("## Core facts\n" + "\n".join(f"- {f}" for f in core))
    if relevant:
        parts.append("## Relevant facts\n" + "\n".join(f"- {f}" for f in relevant))
    return "\n\n".join(parts)


# Session and turn management
def start_session() -> str:
    """Create a new conversation session and return its UUID."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sessions (session_id, created_at, last_active_at)
               VALUES (?, ?, ?)""",
            (session_id, now, now),
        )
    return session_id


def save_turn(
    session_id: str,
    role: str,
    content: str,
    tool_name: str | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO turns (session_id, role, content, tool_name, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, role, content, tool_name, now),
        )
        return cur.lastrowid


def get_session_turns(session_id: str, limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, role, content, tool_name, created_at
               FROM turns
               WHERE session_id = ?
               ORDER BY created_at ASC
               LIMIT ?""",
            (session_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


# Facts REST API functions
def get_fact(fact_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM facts WHERE id = ?",
            (fact_id,),
        ).fetchone()
    if row:
        return dict(row)
    return None


def list_facts(include_archived: bool = False) -> list[dict]:
    with _connect() as conn:
        if include_archived:
            rows = conn.execute(
                "SELECT * FROM facts ORDER BY importance DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM facts WHERE tier != 'archive' ORDER BY importance DESC"
            ).fetchall()
    return [dict(row) for row in rows]


def update_fact(
    fact_id: int,
    content: str | None = None,
    tier: str | None = None,
    importance: float | None = None,
    tags: list[str] | None = None,
) -> bool:
    if all(x is None for x in [content, tier, importance, tags]):
        return False

    updates: list[str] = []
    params: list = []

    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if tier is not None:
        updates.append("tier = ?")
        params.append(tier)
    if importance is not None:
        updates.append("importance = ?")
        params.append(importance)
    if tags is not None:
        updates.append("tags = ?")
        params.append(json.dumps(tags))

    params.append(fact_id)
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE facts SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        return cur.rowcount > 0


def delete_fact(fact_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        return cur.rowcount > 0


# Conversations REST API functions
def list_conversations(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT
                   session_id,
                   (SELECT content FROM turns WHERE session_id = t.session_id AND role = 'user' ORDER BY created_at ASC LIMIT 1) as first_message,
                   COUNT(*) as turn_count,
                   MIN(created_at) as created_at
               FROM turns t
               GROUP BY session_id
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_recent_sessions(limit: int = 5) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT session_id
               FROM turns
               GROUP BY session_id
               ORDER BY MAX(created_at) DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [row["session_id"] for row in rows]


def delete_conversation(session_id: str) -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        return cur.rowcount


def label_session(session_id: str, label: str) -> None:
    """Set the label for a session."""
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET label = ? WHERE session_id = ?",
            (label, session_id),
        )


def close_session(session_id: str, summary: str | None = None) -> None:
    """Close a session and optionally set its summary."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """UPDATE sessions
               SET status = 'closed', summary = ?, last_active_at = ?
               WHERE session_id = ?""",
            (summary, now, session_id),
        )


def set_session_warm(session_id: str) -> None:
    """Mark a session as warm (user stepped away but resumable)."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """UPDATE sessions
               SET status = 'warm', last_active_at = ?
               WHERE session_id = ?""",
            (now, session_id),
        )


def update_session_last_active(session_id: str) -> None:
    """Update the last_active_at timestamp for a session."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET last_active_at = ? WHERE session_id = ?",
            (now, session_id),
        )


def get_session(session_id: str) -> dict | None:
    """Get session metadata by ID."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def search_sessions(query: str, limit: int = 5) -> list[dict]:
    """Keyword search across label + summary of non-open sessions."""
    terms = query.lower().split()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT session_id, label, summary, status, last_active_at
               FROM sessions
               WHERE status IN ('warm', 'closed')
               ORDER BY last_active_at DESC""",
        ).fetchall()

    scored = []
    for row in rows:
        text = ""
        if row["label"]:
            text += row["label"].lower()
        if row["summary"]:
            text += " " + row["summary"].lower()
        hits = sum(1 for t in terms if t in text)
        if hits > 0:
            scored.append((hits, dict(row)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:limit]]
