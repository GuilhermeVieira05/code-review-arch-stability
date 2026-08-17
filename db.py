import sqlite3
import os
from pathlib import Path

def get_connection() -> sqlite3.Connection:
    path = os.environ.get("DB_PATH", "data/mvp.db")
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repos (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            language TEXT NOT NULL,
            stars INTEGER,
            created_at TEXT,
            clone_url TEXT
        );
        CREATE TABLE IF NOT EXISTS quarters (
            repo_id TEXT,
            quarter TEXT,
            review_ratio REAL,
            author_entropy REAL,
            total_prs INTEGER,
            reviewed_prs INTEGER,
            PRIMARY KEY (repo_id, quarter),
            FOREIGN KEY (repo_id) REFERENCES repos(id)
        );
        CREATE TABLE IF NOT EXISTS metrics (
            repo_id TEXT,
            quarter TEXT,
            instability REAL,
            ce REAL,
            ca REAL,
            num_files INTEGER,
            PRIMARY KEY (repo_id, quarter),
            FOREIGN KEY (repo_id) REFERENCES repos(id)
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            repo_id TEXT,
            quarter TEXT,
            status TEXT NOT NULL,
            PRIMARY KEY (repo_id, quarter)
        );
    """)
