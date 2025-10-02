import json
from db import get_db

DEFAULTS = {
    "max_levels": 6,
    "branching": 2,
    "entry_fee": 1000,
    "payout_ratio": 60,
    "market_cap_limit": 50000,
    "payout_depth": 3,
}

def load_config():
    """Load configuration from database or return defaults."""
    cfg = DEFAULTS.copy()
    try:
        with get_db() as con:
            rows = con.execute("SELECT key, value FROM config").fetchall()
            for k, v in rows:
                try:
                    cfg[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    # Keep default if parsing fails
                    pass
    except Exception as e:
        print(f"Error loading config: {e}")
    return cfg

def save_config(new_cfg: dict):
    """Save configuration to database."""
    try:
        with get_db() as con:
            con.execute("DELETE FROM config")
            for k, v in new_cfg.items():
                con.execute(
                    "INSERT INTO config (key, value) VALUES (?, ?)",
                    (k, json.dumps(v)),
                )
            con.commit()
    except Exception as e:
        raise RuntimeError(f"Failed to save config: {e}")
