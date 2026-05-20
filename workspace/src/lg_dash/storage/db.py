from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def db_path() -> Path:
    return Path(os.environ.get("LG_DASH_DB_PATH", "storage/db.sqlite"))


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        p,
        isolation_level=None,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def applied_versions(conn: sqlite3.Connection) -> set[str]:
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        return {r["version"] for r in rows}
    except sqlite3.OperationalError:
        return set()


def migrate(conn: sqlite3.Connection | None = None) -> list[str]:
    own = conn is None
    if own:
        conn = connect()
    try:
        applied = applied_versions(conn)
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        newly_applied: list[str] = []
        for f in files:
            version = f.stem
            if version in applied:
                continue
            conn.executescript(f.read_text(encoding="utf-8"))
            newly_applied.append(version)
        return newly_applied
    finally:
        if own:
            conn.close()
