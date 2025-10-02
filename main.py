import streamlit as st
import sqlite3
from pyramid_app import auth, db, referral, payment

st.set_page_config(page_title="Pyramid App", layout="wide")

# ------------------------------
# Sidebar Authentication
# ------------------------------
def sidebar_auth():
    st.sidebar.title("Authentication")

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.role = None

    if st.session_state.logged_in:
        st.sidebar.success(f"Welcome, {st.session_state.username} ({st.session_state.role})")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.role = None
            st.session_state.logged_out = True
            st.rerun()
    else:
        option = st.sidebar.radio("Choose", ["Login", "Register"])
        if option == "Login":
            username = st.sidebar.text_input("Username")
            password = st.sidebar.text_input("Password", type="password")
            if st.sidebar.button("Login"):
                user = auth.login_user(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = user["role"]
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        else:
            username = st.sidebar.text_input("Choose Username")
            password = st.sidebar.text_input("Choose Password", type="password")
            referrer = st.sidebar.text_input("Referral Username (optional)")
            if st.sidebar.button("Register"):
                ok = auth.register_user(username, password, referrer)
                if ok:
                    st.success("Registered successfully, you can login now.")
                else:
                    st.error("Registration failed (username may already exist).")

# ------------------------------
# User Dashboard
# ------------------------------
def user_dashboard():
    st.title("User Dashboard")
    balance = db.get_balance(st.session_state.username)
    st.metric("Balance", f"{balance} BDT")

    st.subheader("Deposit")
    amount = st.number_input("Deposit Amount", min_value=100, step=50)
    method = st.selectbox("Payment Method", ["nagad", "bkash", "rocket"])
    if st.button("Request Deposit"):
        payment.request_deposit(st.session_state.username, amount, method)
        st.success("Deposit request submitted, pending admin approval.")

    st.subheader("Withdraw")
    amount_w = st.number_input("Withdraw Amount", min_value=100, step=50)
    method_w = st.selectbox("Withdraw Method", ["nagad", "bkash", "rocket"])
    if st.button("Request Withdraw"):
        payment.request_withdraw(st.session_state.username, amount_w, method_w)
        st.success("Withdraw request submitted, pending admin approval.")

    st.subheader("Referrals")
    refs = referral.get_direct_referrals(st.session_state.username)
    st.write("Direct Referrals:", refs)

    st.subheader("Transactions")
    txns = db.get_transactions(st.session_state.username)
    st.table(txns)

# ------------------------------
# Admin Dashboard
# ------------------------------
def admin_dashboard():
    st.title("Admin Panel")

    st.subheader("Pending Deposits")
    deposits = payment.get_pending_deposits()
    for dep in deposits:
        st.write(dep)
        col1, col2 = st.columns(2)
        if col1.button("Approve", key=f"dep_ok_{dep['id']}"):
            payment.approve_deposit(dep['id'])
            st.rerun()
        if col2.button("Reject", key=f"dep_no_{dep['id']}"):
            payment.reject_deposit(dep['id'])
            st.rerun()

    st.subheader("Pending Withdrawals")
    withdraws = payment.get_pending_withdrawals()
    for wd in withdraws:
        st.write(wd)
        col1, col2 = st.columns(2)
        if col1.button("Approve", key=f"wd_ok_{wd['id']}"):
            payment.approve_withdraw(wd['id'])
            st.rerun()
        if col2.button("Reject", key=f"wd_no_{wd['id']}"):
            payment.reject_withdraw(wd['id'])
            st.rerun()

    st.subheader("Analytics")
    st.metric("Total Users", db.count_users())
    st.metric("Total Deposits", db.total_deposits())
    st.metric("Total Withdrawals", db.total_withdrawals())

# ------------------------------
# Main App
# ------------------------------
def main():
    sidebar_auth()
    if st.session_state.get("logged_in"):
        if st.session_state.role == "admin":
            admin_dashboard()
        else:
            user_dashboard()
    else:
        st.title("Welcome to Pyramid App")
        st.write("Please login or register from the sidebar.")

if __name__ == "__main__":
    main()
