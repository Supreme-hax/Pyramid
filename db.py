# pyramid_app/db.py
"""
Database layer.
- Default: SQLite local file pyramid_app.db
- Optional: use DATABASE_URL (Postgres/MySQL) via SQLAlchemy if provided in st.secrets or env
Provides:
- get_conn() contextmanager returning sqlite3.Connection (or SQLAlchemy if extended)
- init_db() to create schema
- helpers for migrations/backups
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import json
import streamlit as st
from datetime import datetime

BASE = Path(__file__).parent
DEFAULT_DB = BASE / "pyramid_app.db"
DB_PATH = Path(os.getenv("PYRAMID_DB", DEFAULT_DB))

# Ensure folder exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

@contextmanager
def get_db():
    """Context manager returning sqlite3 connection with row_factory dict-like access."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize DB schema if not exists."""
    schema = r"""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        balance REAL DEFAULT 0,
        parent_id INTEGER,
        level INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user', -- user|admin|staff
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        type TEXT NOT NULL, -- deposit, withdrawal, commission, adjustment
        method TEXT, -- nagad, bkash, rocket, admin, system
        amount REAL NOT NULL,
        status TEXT DEFAULT 'pending', -- pending, approved, rejected
        note TEXT,
        source_tx_id INTEGER, -- for commission idempotency relation
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY(member_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_users_parent ON users(parent_id);
    CREATE INDEX IF NOT EXISTS idx_tx_member ON transactions(member_id);
    CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(status);
    """
    with get_db() as con:
        con.executescript(schema)
        con.commit()

def get_config(key, default=None):
    with get_db() as con:
        cur = con.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cur.fetchone()
        if row:
            return json.loads(row["value"])
        return default

def set_config(key, value):
    with get_db() as con:
        con.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        con.commit()

def backup_db_bytes():
    """Return bytes of DB file for download/backup."""
    with open(DB_PATH, "rb") as f:
        return f.read()

# initialize at import if missing
if not DB_PATH.exists():
    init_db()
    # default commission_rates setting (levels 1..3)
    set_config("commission_rates", [0.10, 0.05, 0.02])
    set_config("max_levels", 10)
    set_config("branching", 3)
