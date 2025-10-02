import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path("pyramid.db")

@contextmanager
def get_db():
    """Context manager for database connections."""
    con = sqlite3.connect(DB_PATH, timeout=10.0)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()

def init_db():
    """Initialize database schema."""
    schema = """
    CREATE TABLE IF NOT EXISTS members (
        id TEXT PRIMARY KEY,
        level INTEGER NOT NULL,
        parent TEXT,
        joined_at INTEGER NOT NULL,
        paid INTEGER NOT NULL,
        payout REAL DEFAULT 0,
        name TEXT,
        FOREIGN KEY(parent) REFERENCES members(id)
    );
    
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id TEXT NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('inflow','outflow')),
        amount INTEGER NOT NULL,
        ts INTEGER NOT NULL,
        stripe_session TEXT,
        FOREIGN KEY(member_id) REFERENCES members(id)
    );
    
    CREATE INDEX IF NOT EXISTS idx_members_level ON members(level);
    CREATE INDEX IF NOT EXISTS idx_members_parent ON members(parent);
    CREATE INDEX IF NOT EXISTS idx_transactions_member ON transactions(member_id);
    CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
    """
    with get_db() as con:
        con.executescript(schema)
        con.commit()

# Initialize database on import
if not DB_PATH.exists():
    init_db()
