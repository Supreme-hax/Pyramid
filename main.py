# main.py  (Streamlit entrypoint)
import streamlit as st
from pyramid_app import auth, db, payment, referral, ui, config
from pyramid_app.db import get_db
import pandas as pd
import io

st.set_page_config(page_title="Pyramid App", layout="wide")

# Ensure DB ready
db.init_db()

# Sidebar: Owner login + user auth
is_owner = auth.owner_login_widget()

def sidebar_user_auth():
    st.sidebar.title("Account")
    if st.session_state.get("user_id"):
        uid = st.session_state["user_id"]
        with get_db() as con:
            u = con.execute("SELECT username, balance FROM users WHERE id = ?", (uid,)).fetchone()
        st.sidebar.markdown(f"**{u['username']}**\n\nBalance: ৳{u['balance']:,}")
        if st.sidebar.button("Logout"):
            del st.session_state["user_id"]
            st.rerun()
    else:
        mode = st.sidebar.radio("Action", ["Login","Register"])
        if mode == "Login":
            username = st.sidebar.text_input("Username", key="login_user")
            password = st.sidebar.text_input("Password", type="password", key="login_pass")
            if st.sidebar.button("Login", key="login_btn"):
                user = auth.authenticate(username, password)
                if user:
                    st.session_state["user_id"] = user["id"]
                    st.success("Logged in")
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        else:
            new_user = st.sidebar.text_input("Choose username", key="reg_user")
            new_pass = st.sidebar.text_input("Choose password", type="password", key="reg_pass")
            ref = st.sidebar.text_input("Referral username (optional)", key="reg_ref")
            if st.sidebar.button("Register", key="reg_btn"):
                try:
                    auth.register_user(new_user, new_pass, referrer_username=ref if ref else None)
                    st.success("Registration successful. Please login.")
                except Exception as e:
                    st.error(f"Error: {e}")

sidebar_user_auth()

st.title("Pyramid / Referral App")

# show owner-only controls in sidebar
if is_owner:
    st.sidebar.success("Owner mode active")
    admin_view = st.sidebar.selectbox("Owner views", ["Owner Dashboard","Config","Backup DB"])
    if admin_view == "Config":
        st.header("Configuration")
        rates = config.get_commission_rates()
        st.write("Current commission rates (level1, level2, ...):", rates)
        new = st.text_input("Comma separated rates", value=",".join(str(r) for r in rates))
        if st.button("Save rates"):
            try:
                parsed = [float(x.strip()) for x in new.split(",") if x.strip()]
                config.set_commission_rates(parsed)
                st.success("Saved")
            except Exception as e:
                st.error("Invalid format")
    elif admin_view == "Backup DB":
        st.header("Database Backup")
        b = db.backup_db_bytes()
        st.download_button("Download DB Backup", b, file_name="pyramid_app.db")
    else:
        st.header("Owner Dashboard")
        ui.kpi_cards()
        st.markdown("### Pending Transactions")
        with get_db() as con:
            pend = con.execute("SELECT t.*, u.username FROM transactions t LEFT JOIN users u ON u.id = t.member_id WHERE t.status='pending' ORDER BY created_at DESC").fetchall()
        for tx in pend:
            st.write(dict(tx))
            col1, col2 = st.columns([1,1])
            if col1.button(f"Approve {tx['id']}", key=f"app_{tx['id']}"):
                try:
                    payment.approve_transaction(tx["id"], approver=st.secrets.get("owner", {}).get("name", "owner"))
                    st.success("Approved")
                    st.rerun()
                except Exception as e:
                    st.error(f"Approve failed: {e}")
            if col2.button(f"Reject {tx['id']}", key=f"rej_{tx['id']}"):
                payment.reject_transaction(tx["id"], reason="Rejected by owner")
                st.warning("Rejected")
                st.rerun()

# Regular user view
if st.session_state.get("user_id"):
    uid = st.session_state["user_id"]
    st.header("User Dashboard")
    with get_db() as con:
        user = con.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    st.subheader(f"Welcome, {user['username']}")
    st.metric("Balance (৳)", f"{user['balance']:,}")

    # Deposit/Withdraw forms
    st.markdown("#### Deposit Request (Manual)")
    dep_col1, dep_col2 = st.columns(2)
    with dep_col1:
        dep_amt = st.number_input("Amount (৳)", min_value=10.0, step=10.0, key="dep_amt")
        dep_method = st.selectbox("Method", ["nagad","bkash","rocket"], key="dep_method")
        dep_note = st.text_input("Note / txn id (optional)", key="dep_note")
        if st.button("Request Deposit", key="req_dep"):
            txid = payment.create_transaction(uid, "deposit", float(dep_amt), method=dep_method, note=dep_note)
            st.success(f"Deposit requested (tx id {txid}). Admin will approve.")

    with dep_col2:
        w_amt = st.number_input("Withdraw amount (৳)", min_value=50.0, step=50.0, key="w_amt")
        w_method = st.selectbox("Withdraw method", ["nagad","bkash","rocket"], key="w_method")
        w_note = st.text_input("Withdraw note / mobile", key="w_note")
        if st.button("Request Withdraw", key="req_w"):
            if user["balance"] is None or user["balance"] < float(w_amt):
                st.error("Insufficient balance")
            else:
                payment.create_transaction(uid, "withdrawal", float(w_amt), method=w_method, note=w_note)
                st.success("Withdrawal requested. Admin will process it.")

    st.markdown("#### Your transactions")
    df = ui.transactions_df(limit=500)
    df_user = df[df["member_id"] == uid] if not df.empty else df
    if not df_user.empty:
        st.dataframe(df_user)
        st.download_button("Download my transactions CSV", df_user.to_csv(index=False).encode(), file_name=f"{user['username']}_transactions.csv")
    else:
        st.info("No transactions yet.")

    st.markdown("#### Your referrals")
    refs = referral.get_direct_referrals(uid)
    if refs:
        for r in refs:
            st.write(f"{r['username']} — joined {r['created_at']}")
    else:
        st.info("No referrals yet.")
else:
    st.info("Please login or register from the sidebar to use the app.")

# Analytics section public/basic
st.sidebar.markdown("---")
if st.sidebar.checkbox("Show analytics"):
    st.header("Analytics")
    ui.kpi_cards()
    ui.simple_deposit_withdraw_chart()
    ui.export_transactions_csv()
