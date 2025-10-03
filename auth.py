# ============================================================================
# auth.py - FIXED IMPORTS
# ============================================================================
"""
Authentication utilities:
- register_user(username, password, email, referrer_username)
- authenticate(username, password) -> user_row or None
- get_user_by_id / by_username
- owner_login (uses st.secrets["owner"])
"""

import os
import hashlib
import binascii
from typing import Optional
import streamlit as st
from db import get_db  # CHANGED: removed relative import

# PBKDF2 params
ITERATIONS = 200_000

def _make_salt() -> str:
    return binascii.hexlify(os.urandom(16)).decode()

def _hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return binascii.hexlify(dk).decode()

def register_user(username: str, password: str, email: Optional[str]=None, referrer_username: Optional[str]=None):
    salt = _make_salt()
    ph = _hash_password(password, salt)
    parent_id = None
    level = 0
    if referrer_username:
        with get_db() as con:
            cur = con.execute("SELECT id, level FROM users WHERE username = ?", (referrer_username,))
            r = cur.fetchone()
            if r:
                parent_id = r["id"]
                level = (r["level"] or 0) + 1
    with get_db() as con:
        con.execute(
            "INSERT INTO users (username, email, password_hash, salt, parent_id, level) VALUES (?, ?, ?, ?, ?, ?)",
            (username, email, ph, salt, parent_id, level)
        )
        con.commit()
    return True

def authenticate(username: str, password: str):
    with get_db() as con:
        cur = con.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if not row:
            return None
        expected = _hash_password(password, row["salt"])
        if expected == row["password_hash"]:
            return row
    return None

def get_user_by_id(uid: int):
    with get_db() as con:
        return con.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

def get_user_by_username(username: str):
    with get_db() as con:
        return con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

def owner_login_widget():
    """Sidebar owner login form. Returns True if owner logged in (st.session_state['owner'])"""
    if st.session_state.get("owner"):
        return True
    with st.sidebar.expander("🔐 Owner login", expanded=False):
        name = st.text_input("Owner name", key="owner_name_input")
        key  = st.text_input("Secret key", type="password", key="owner_key_input")
        if st.button("Login", key="owner_login_btn"):
            try:
                secret_name = st.secrets["owner"]["name"]
                secret_key  = st.secrets["owner"]["key"]
                if name == secret_name and key == secret_key:
                    st.session_state["owner"] = name
                    st.success("Logged in as owner")
                    st.rerun()
                else:
                    st.error("Invalid owner credentials")
            except KeyError:
                st.error("⚠️ Secrets not configured. Add owner credentials in Streamlit Secrets.")
    return False
