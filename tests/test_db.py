import os
import pytest

os.environ["DB_PATH"] = ":memory:"

from db import init_db, get_connection

def test_init_creates_all_tables():
    with get_connection() as conn:
        init_db(conn)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert tables == {"repos", "quarters", "metrics", "snapshots"}

def test_init_is_idempotent():
    with get_connection() as conn:
        init_db(conn)
        init_db(conn)  # must not raise
