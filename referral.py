# pyramid_app/referral.py
"""
Referral utilities:
- register_referral chain queries
- get_direct_referrals(user_id)
- get_parent_chain(user_id, max_levels)
- referral_tree(user_id, depth) -> nested dict for visualization
"""

from .db import get_db, get_config
from typing import List, Dict

def get_direct_referrals(user_id: int):
    with get_db() as con:
        rows = con.execute("SELECT id, username, level, created_at FROM users WHERE parent_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return rows

def get_parent_chain(user_id:int, max_levels:int=None) -> List[int]:
    if max_levels is None:
        max_levels = get_config("max_levels", 10)
    chain = []
    cur_id = user_id
    with get_db() as con:
        for i in range(max_levels):
            r = con.execute("SELECT parent_id FROM users WHERE id = ?", (cur_id,)).fetchone()
            if not r or not r["parent_id"]:
                break
            pid = r["parent_id"]
            chain.append(pid)
            cur_id = pid
    return chain

def referral_tree(user_id:int, depth=3) -> Dict:
    """Return nested tree: {'id':..., 'username':..., 'children':[...]}"""
    with get_db() as con:
        root = con.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        if not root:
            return {}
    def build(node_id, current_depth):
        with get_db() as con:
            children = con.execute("SELECT id, username FROM users WHERE parent_id = ?", (node_id,)).fetchall()
        if current_depth >= depth:
            return {"id": node_id, "children": [{"id": c["id"], "username": c["username"]} for c in children]}
        return {"id": node_id, "username": get_username(node_id), "children":[build(c["id"], current_depth+1) for c in children]}
    return build(user_id, 0)

def get_username(user_id):
    with get_db() as con:
        r = con.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        return r["username"] if r else None
