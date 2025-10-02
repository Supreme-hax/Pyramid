import streamlit as st
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
import hashlib, os, json

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "pyramid_app.db"

# --------------------- Database helpers ---------------------
@contextmanager
def get_db():
    con = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()

def init_db():
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT,
        password_hash TEXT,
        salt TEXT,
        balance REAL DEFAULT 0,
        parent_id INTEGER,
        joined_at TEXT,
        level INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        type TEXT, -- deposit, withdrawal, commission, adjustment
        method TEXT, -- nagad, bkash, rocket, admin
        amount REAL,
        status TEXT, -- pending, approved, rejected
        note TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    );
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

# --------------------- Security ---------------------
def make_salt():
    return os.urandom(16).hex()

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()

# --------------------- User Management ---------------------
def register_user(username, password, email=None, parent_username=None):
    salt = make_salt()
    ph = hash_password(password, salt)
    parent_id = None
    level = 0
    if parent_username:
        with get_db() as con:
            cur = con.execute("SELECT id, level FROM users WHERE username = ?", (parent_username,))
            parent = cur.fetchone()
            if parent:
                parent_id = parent["id"]
                level = parent["level"] + 1
    joined = datetime.utcnow().isoformat()
    with get_db() as con:
        con.execute("INSERT INTO users (username, email, password_hash, salt, parent_id, joined_at, level) VALUES (?,?,?,?,?,?,?)",
                    (username, email, ph, salt, parent_id, joined, level))
        con.commit()
    return True

def authenticate(username, password):
    with get_db() as con:
        cur = con.execute("SELECT id, password_hash, salt FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if not row:
            return None
        ph = hash_password(password, row["salt"])
        if ph == row["password_hash"]:
            return row["id"]
    return None

def get_user(user_id):
    with get_db() as con:
        cur = con.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()

def get_user_by_username(username):
    with get_db() as con:
        cur = con.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()

# --------------------- Transactions ---------------------
def create_transaction(member_id, type_, amount, method="manual", status="pending", note=None):
    now = datetime.utcnow().isoformat()
    with get_db() as con:
        con.execute("INSERT INTO transactions (member_id, type, method, amount, status, note, created_at) VALUES (?,?,?,?,?,?,?)",
                    (member_id, type_, method, amount, status, note, now))
        con.commit()
        return con.execute("SELECT last_insert_rowid() as id").fetchone()["id"]

def list_transactions(member_id=None, status=None, type_=None, limit=100):
    q = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if member_id:
        q += " AND member_id = ?"
        params.append(member_id)
    if status:
        q += " AND status = ?"
        params.append(status)
    if type_:
        q += " AND type = ?"
        params.append(type_)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with get_db() as con:
        cur = con.execute(q, tuple(params))
        return cur.fetchall()

def change_transaction_status(tx_id, new_status, admin_note=None):
    with get_db() as con:
        con.execute("UPDATE transactions SET status = ?, note = COALESCE(note, '') || ? WHERE id = ?", (new_status, f" | {admin_note}" if admin_note else "", tx_id))
        con.commit()
        cur = con.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
        tx = cur.fetchone()
    # If approved and deposit -> credit user and distribute commissions
    if tx and new_status == "approved":
        if tx["type"] == "deposit":
            credit_user(tx["member_id"], tx["amount"])
            distribute_commissions(tx["member_id"], tx["amount"], tx["id"])
        elif tx["type"] == "withdrawal":
            # already deducted on admin approve or at request time depending on policy
            pass
    return tx

def credit_user(user_id, amount):
    with get_db() as con:
        con.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        con.commit()

def debit_user(user_id, amount):
    with get_db() as con:
        con.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, user_id))
        con.commit()

# --------------------- Referral + Commission ---------------------
def get_parent_chain(user_id, max_levels=5):
    chain = []
    current = user_id
    with get_db() as con:
        for i in range(max_levels):
            cur = con.execute("SELECT parent_id FROM users WHERE id = ?", (current,))
            row = cur.fetchone()
            if not row or not row["parent_id"]:
                break
            pid = row["parent_id"]
            chain.append(pid)
            current = pid
    return chain  # [parent_level1, parent_level2, ...]

def distribute_commissions(member_id, amount, source_tx_id=None):
    # Commission structure (levels 1..n)
    commission_rates = get_config("commission_rates", [0.10, 0.05, 0.02])
    parents = get_parent_chain(member_id, max_levels=len(commission_rates))
    for idx, parent_id in enumerate(parents):
        rate = commission_rates[idx] if idx < len(commission_rates) else 0
        if rate <= 0:
            continue
        comm_amount = round(amount * rate, 2)
        if comm_amount <= 0:
            continue
        # credit parent account
        credit_user(parent_id, comm_amount)
        # record transaction
        note = f"Commission level {idx+1} from member {member_id} (source tx {source_tx_id})"
        create_transaction(parent_id, "commission", comm_amount, method="system", status="approved", note=note)

# --------------------- Utilities / Admin ---------------------
def ensure_sample_data():
    # create an owner if not exists for demonstration (owner is controlled by Streamlit secrets)
    owner_name = None
    try:
        owner_name = st.secrets["owner"]["name"]
    except Exception:
        pass
    if owner_name and not get_user_by_username(owner_name):
        # create a user record for owner (no password)
        salt = make_salt()
        ph = hash_password("owner_password", salt)
        with get_db() as con:
            con.execute("INSERT OR IGNORE INTO users (username, email, password_hash, salt, joined_at, level) VALUES (?,?,?,?,?,?)",
                        (owner_name, None, ph, salt, datetime.utcnow().isoformat(), 0))
            con.commit()

def list_users(limit=200):
    with get_db() as con:
        cur = con.execute("SELECT * FROM users ORDER BY id DESC LIMIT ?", (limit,))
        return cur.fetchall()

def user_referrals(user_id):
    with get_db() as con:
        cur = con.execute("SELECT * FROM users WHERE parent_id = ? ORDER BY joined_at DESC", (user_id,))
        return cur.fetchall()

# --------------------- Streamlit UI ---------------------
def sidebar_auth():
    st.sidebar.title("Authentication")
    if st.session_state.get("user_id"):
        u = get_user(st.session_state["user_id"])
        st.sidebar.markdown(f"**Logged in as:** {u['username']}  \nBalance: ৳{u['balance']:,}")
        if st.sidebar.button("Logout"):
            del st.session_state["user_id"]
            st.experimental_rerun()
    else:
        tab = st.sidebar.radio("Choose", ["Login","Register"])
        if tab == "Login":
            username = st.sidebar.text_input("Username", key="login_user")
            password = st.sidebar.text_input("Password", type="password", key="login_pass")
            if st.sidebar.button("Login", key="login_btn"):
                uid = authenticate(username, password)
                if uid:
                    st.session_state["user_id"] = uid
                    st.sidebar.success("Logged in")
                    st.experimental_rerun()
                else:
                    st.sidebar.error("Invalid credentials")
        else:
            new_user = st.sidebar.text_input("Choose username", key="reg_user")
            new_pass = st.sidebar.text_input("Choose password", type="password", key="reg_pass")
            ref = st.sidebar.text_input("Referral (username)", key="reg_ref")
            if st.sidebar.button("Register", key="reg_btn"):
                if not new_user or not new_pass:
                    st.sidebar.error("Username and password required")
                elif get_user_by_username(new_user):
                    st.sidebar.error("Username already exists")
                else:
                    register_user(new_user, new_pass, parent_username=ref or None)
                    st.sidebar.success("Registration complete. Please login.")
# Main views
def user_dashboard(user_id):
    st.header("Multi-user Dashboard")
    u = get_user(user_id)
    st.subheader(f"Welcome, {u['username']}")
    st.metric("Balance (৳)", f"{u['balance']:,}")
    st.write("Joined:", u["joined_at"])
    # Quick actions
    st.markdown("### Actions")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Deposit (manual)")
        dep_amt = st.number_input("Amount (৳)", min_value=10.0, step=10.0, key="dep_amt")
        dep_method = st.selectbox("Method", ["nagad","bkash","rocket"], key="dep_method")
        dep_note = st.text_input("Note / txn id (optional)", key="dep_note")
        if st.button("Request Deposit", key="req_dep"):
            txid = create_transaction(user_id, "deposit", dep_amt, method=dep_method, status="pending", note=dep_note)
            st.success(f"Deposit requested (tx id {txid}). Admin will approve.")
    with col2:
        st.markdown("#### Withdraw (manual)")
        w_amt = st.number_input("Amount (৳)", min_value=50.0, step=50.0, key="w_amt")
        w_method = st.selectbox("Method", ["nagad","bkash","rocket"], key="w_method")
        w_note = st.text_input("Withdraw note / mobile", key="w_note")
        if st.button("Request Withdraw", key="req_w"):
            # check balance
            if u["balance"] is None or u["balance"] < w_amt:
                st.error("Insufficient balance")
            else:
                # create withdrawal as pending; optionally debit immediately or on approval
                create_transaction(user_id, "withdrawal", w_amt, method=w_method, status="pending", note=w_note)
                st.success("Withdrawal requested. Admin will process it.")
    st.markdown("### Transactions")
    txs = list_transactions(member_id=user_id, limit=200)
    if txs:
        for t in txs:
            st.write(dict(t))
    else:
        st.info("No transactions yet.")
    st.markdown("### Referrals")
    refs = user_referrals(user_id)
    st.write(f"Direct referrals ({len(refs)}):")
    for r in refs:
        st.write(dict(r))

def admin_panel():
    st.header("Admin Panel")
    # Owner check
    try:
        owner_name = st.secrets["owner"]["name"]
    except Exception:
        owner_name = None
    st.write("Owner:", owner_name or "(not set in secrets)")
    # Quick stats
    with get_db() as con:
        total_users = con.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        total_deposits = con.execute("SELECT SUM(amount) as s FROM transactions WHERE type='deposit' AND status='approved'").fetchone()["s"] or 0.0
        total_withdraw = con.execute("SELECT SUM(amount) as s FROM transactions WHERE type='withdrawal' AND status='approved'").fetchone()["s"] or 0.0
    st.metric("Total users", total_users)
    st.metric("Total approved deposits (৳)", f"{total_deposits:,}")
    st.metric("Total approved withdrawals (৳)", f"{total_withdraw:,}")

    st.markdown("### Pending Transactions")
    pend = list_transactions(status="pending", limit=500)
    for t in pend:
        cols = st.columns([1,1,2,1,1,2])
        cols[0].write(t["id"])
        cols[1].write(t["member_id"])
        cols[2].write(t["type"])
        cols[3].write(f"৳{t['amount']}")
        cols[4].write(t["method"])
        if cols[5].button("Approve", key=f"app_{t['id']}"):
            # Approve: credit or debit accordingly
            if t["type"] == "deposit":
                change_transaction_status(t["id"], "approved", admin_note=f"Approved by admin")
                st.experimental_rerun()
            elif t["type"] == "withdrawal":
                # ensure user has balance
                user = get_user(t["member_id"])
                if user["balance"] >= t["amount"]:
                    # debit and mark approved
                    debit_user(user["id"], t["amount"])
                    change_transaction_status(t["id"], "approved", admin_note=f"Approved by admin")
                    st.experimental_rerun()
                else:
                    st.error("Insufficient balance to approve withdrawal")
        if cols[5].button("Reject", key=f"rej_{t['id']}"):
            change_transaction_status(t["id"], "rejected", admin_note="Rejected by admin")
            st.experimental_rerun()

    st.markdown("### Users")
    users = list_users(500)
    for u in users:
        st.write(dict(u))

# --------------------- App Initialization ---------------------
if not DB_PATH.exists():
    init_db()
    # set default commission config if not set
    set_config("commission_rates", [0.10, 0.05, 0.02])

ensure_sample_data()

# --------------------- Page routing ---------------------
st.set_page_config(page_title="Pyramid App", layout="wide")
st.title("Pyramid / Referral App (Streamlit)")

# Owner login (sidebar)
from auth import owner_login
is_owner = owner_login()

sidebar_auth()

if is_owner:
    st.sidebar.success("Owner mode active")
    view = st.sidebar.selectbox("Admin Views", ["Dashboard","Admin Panel","Config"])
    if view == "Admin Panel":
        admin_panel()
    elif view == "Config":
        st.header("Config")
        comm = get_config("commission_rates", [0.10,0.05,0.02])
        st.write("Commission rates (level1, level2, ...):", comm)
        new = st.text_input("New comma-separated rates (e.g. 0.1,0.05,0.02)", key="cfg_rates")
        if st.button("Save config"):
            try:
                rates = [float(x.strip()) for x in new.split(",") if x.strip()]
                set_config("commission_rates", rates)
                st.success("Saved")
            except Exception as e:
                st.error("Invalid input")
    else:
        st.header("Owner Dashboard")
        admin_panel()
else:
    # normal user view
    if st.session_state.get("user_id"):
        user_dashboard(st.session_state["user_id"])
    else:
        st.info("Please login or register from the sidebar to use the app.")
