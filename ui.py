# ============================================================================
# ui.py - FIXED IMPORTS
# ============================================================================
"""
UI helper functions: kpi_cards, transactions_table, referrals_tree_visual (text),
export_csv, basic charts (matplotlib).
"""

import streamlit as st
from db import get_db  # CHANGED: removed relative import
import pandas as pd
import io
import matplotlib.pyplot as plt

def kpi_cards():
    with get_db() as con:
        total_users = con.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        total_deposits = con.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE type='deposit' AND status='approved'").fetchone()["s"]
        total_withdrawals = con.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE type='withdrawal' AND status='approved'").fetchone()["s"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Total users", f"{total_users:,}")
    c2.metric("Approved deposits (৳)", f"{total_deposits:,}")
    c3.metric("Approved withdrawals (৳)", f"{total_withdrawals:,}")

def transactions_df(limit=500):
    with get_db() as con:
        rows = con.execute("SELECT t.*, u.username FROM transactions t LEFT JOIN users u ON u.id = t.member_id ORDER BY t.created_at DESC LIMIT ?", (limit,)).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    return df

def export_transactions_csv():
    df = transactions_df(10000)
    if df.empty:
        st.info("No transactions to export.")
        return
    csv = df.to_csv(index=False)
    b = csv.encode()
    st.download_button("Download Transactions CSV", b, file_name="transactions.csv", mime="text/csv")

def simple_deposit_withdraw_chart():
    with get_db() as con:
        rows = con.execute("SELECT date(created_at) as d, SUM(CASE WHEN type='deposit' AND status='approved' THEN amount ELSE 0 END) as deposits, SUM(CASE WHEN type='withdrawal' AND status='approved' THEN amount ELSE 0 END) as withdraws FROM transactions GROUP BY date(created_at) ORDER BY d DESC LIMIT 30").fetchall()
    if not rows:
        st.info("No data to plot")
        return
    df = pd.DataFrame([dict(r) for r in rows])
    df = df.sort_values("d")
    plt.figure()
    plt.plot(df["d"], df["deposits"])
    plt.plot(df["d"], df["withdraws"])
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(plt)
