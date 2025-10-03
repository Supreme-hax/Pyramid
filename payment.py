# pyramid_app/payment.py
"""
Payment & transaction logic:
- create_transaction(member_id, type_, amount, method, note)
- approve_transaction(tx_id, approver_is_admin=True) -> does credit/debit and commission distribution
- reject_transaction(tx_id)
- idempotency safeguards for commission distribution (checks source_tx_id)
- credit_user / debit_user low-level helpers
"""

from .db import get_db, get_config, set_config
from datetime import datetime
from .referral import get_parent_chain
import json

def create_transaction(member_id:int, type_:str, amount:float, method:str="manual", note:str=None, source_tx_id=None):
    now = datetime.utcnow().isoformat()
    with get_db() as con:
        cur = con.execute(
            "INSERT INTO transactions (member_id, type, method, amount, status, note, source_tx_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (member_id, type_, method, amount, "pending", note, source_tx_id, now)
        )
        con.commit()
        return cur.lastrowid

def list_transactions(member_id=None, status=None, type_=None, limit=200):
    q = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if member_id:
        q += " AND member_id = ?"; params.append(member_id)
    if status:
        q += " AND status = ?"; params.append(status)
    if type_:
        q += " AND type = ?"; params.append(type_)
    q += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
    with get_db() as con:
        return con.execute(q, tuple(params)).fetchall()

def _credit_user(con, user_id:int, amount:float):
    con.execute("UPDATE users SET balance = COALESCE(balance,0) + ? WHERE id = ?", (amount, user_id))

def _debit_user(con, user_id:int, amount:float):
    con.execute("UPDATE users SET balance = COALESCE(balance,0) - ? WHERE id = ?", (amount, user_id))

def _record_transaction(con, member_id, amount, type_, method, status, note, source_tx_id=None):
    now = datetime.utcnow().isoformat()
    con.execute("INSERT INTO transactions (member_id, type, method, amount, status, note, source_tx_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (member_id, type_, method, amount, status, note, source_tx_id, now))

def approve_transaction(tx_id:int, approver="admin"):
    """
    Approve pending tx:
     - deposit: credit user + distribute commissions (idempotent)
     - withdrawal: debit user (if not already debited) and mark approved
     - commission/adjustment: handled as recorded
    """
    with get_db() as con:
        tx = con.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if not tx:
            raise ValueError("Transaction not found")
        if tx["status"] == "approved":
            return tx  # already approved
        # begin atomic block
        try:
            con.execute("BEGIN")
            if tx["type"] == "deposit":
                _credit_user(con, tx["member_id"], tx["amount"])
                # mark the original transaction as approved
                con.execute("UPDATE transactions SET status='approved', note=COALESCE(note,'') || ? WHERE id = ?", (f" | approved_by:{approver}", tx_id))
                # record commission distribution (ensure idempotent by checking commission presence for source_tx_id)
                distribute_commissions(con, tx["member_id"], tx["amount"], source_tx_id=tx_id)
            elif tx["type"] == "withdrawal":
                # check balance and debit
                curbal = con.execute("SELECT balance FROM users WHERE id = ?", (tx["member_id"],)).fetchone()["balance"] or 0
                if curbal < tx["amount"]:
                    raise ValueError("Insufficient balance to approve withdrawal")
                _debit_user(con, tx["member_id"], tx["amount"])
                con.execute("UPDATE transactions SET status='approved', note=COALESCE(note,'') || ? WHERE id = ?", (f" | approved_by:{approver}", tx_id))
            else:
                # generic approve
                con.execute("UPDATE transactions SET status='approved', note=COALESCE(note,'') || ? WHERE id = ?", (f" | approved_by:{approver}", tx_id))
            con.commit()
            return con.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        except Exception as e:
            con.rollback()
            raise

def reject_transaction(tx_id:int, reason:str=None):
    with get_db() as con:
        con.execute("UPDATE transactions SET status='rejected', note = COALESCE(note,'') || ? WHERE id = ?", (f" | rejected: {reason}" if reason else " | rejected", tx_id))
        con.commit()

def distribute_commissions(con, member_id:int, amount:float, source_tx_id:int=None):
    """
    Distribute commissions up the parent chain according to stored commission_rates.
    - IDENTITY: check whether commission entries for given source_tx_id already exist to prevent double-credit.
    - con: an open sqlite connection in transaction
    """
    rates = get_config("commission_rates", [0.10, 0.05, 0.02]) or [0.10, 0.05, 0.02]
    parents = []
    # gather parent chain
    cur = con.execute("SELECT parent_id FROM users WHERE id = ?", (member_id,)).fetchone()
    current = cur["parent_id"] if cur else None
    while current and len(parents) < len(rates):
        parents.append(current)
        cur = con.execute("SELECT parent_id FROM users WHERE id = ?", (current,)).fetchone()
        current = cur["parent_id"] if cur else None

    # idempotency guard: if source_tx_id is provided, check whether any commission rows exist referencing it
    if source_tx_id is not None:
        exists = con.execute("SELECT COUNT(*) as c FROM transactions WHERE type='commission' AND source_tx_id = ?", (source_tx_id,)).fetchone()["c"]
        if exists and exists > 0:
            return  # already processed

    for idx, parent_id in enumerate(parents):
        rate = rates[idx] if idx < len(rates) else 0
        if rate <= 0:
            continue
        comm_amount = round(amount * rate, 2)
        if comm_amount <= 0:
            continue
        # credit parent and write commission tx (approved)
        _credit_user(con, parent_id, comm_amount)
        _record_transaction(con, parent_id, comm_amount, "commission", "system", "approved", f"Level {idx+1} commission from member {member_id}", source_tx_id)
    # note: commit handled by outer transaction
