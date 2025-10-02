import streamlit as st
from auth import owner_login
from config import load_config, save_config
from payment import start_checkout, verify_and_record
from referral import register_member, distribute_payouts
from ui import (
    kpi_cards,
    inflow_outflow_chart,
    level_bar_chart,
    tree_view,
    members_table,
)

# ------------------------
# Page config & style
# ------------------------
st.set_page_config(page_title="এডভান্স পিরামিড স্কিম", layout="wide")
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;600;700&display=swap');
html,body,[class*="css"]{font-family:'Noto Sans Bengali',sans-serif;}
:root{--primary:#FFD700;--secondary:#1E90FF;--bg:#F7F9FC;--card:#FFFFFF;--text:#0F172A;}
body{background-color:var(--bg);} .card{background:var(--card);border-radius:16px;padding:16px;box-shadow:0 8px 24px rgba(16,24,40,.06);border:1px solid #EEF2F7;}
h1,h2,h3,h4{color:var(--text);} .badge{display:inline-block;padding:6px 10px;border-radius:999px;font-size:.9rem;font-weight:600;background:#FFF1B8;color:#7C5800;border:1px solid #FFE58F;}
.warn{background:#FEF3C7;color:#92400E;border:1px solid #FDE68A;}
.ok{background:#ECFDF5;color:#065F46;border:1px solid #A7F3D0;}
.kpi{border-radius:14px;padding:16px;background:linear-gradient(180deg,#FFF,#FFFDF3);border:1px solid #F1F5F9;}
.kpi h3{margin:0 0 6px 0;font-weight:700;}
.kpi .val{font-size:1.6rem;font-weight:700;color:#0F172A;}
footer{visibility:hidden;}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🔺 এডভান্স পিরামিড স্কিম")
st.markdown("<p class='badge warn'>শিক্ষামূলক ডেমো – বাস্তব অর্থ লেনদেনের জন্য সম্পূর্ণ কনফিগারেশন দরকার।</p>", unsafe_allow_html=True)

# ---------- Owner login ----------
if not owner_login():
    st.info("⚙️ Owner‑only controls are hidden. Log in from the sidebar to manage the scheme.")
else:
    st.success("✅ Logged in as owner")

# ---------- Config (owner‑only) ----------
cfg = load_config()
if st.session_state.get("owner"):
    with st.sidebar.expander("⚙️ Owner Settings", expanded=False):
        max_levels = st.slider("মোট লেভেল", 2, 12, cfg["max_levels"])
        branching = st.slider("ব্রাঞ্চিং (প্রতি সদস্য কতজনকে রেফার করতে পারে)", 1, 5, cfg["branching"])
        entry_fee = st.number_input("এন্ট্রি ফি (৳)", min_value=100, value=cfg["entry_fee"], step=100)
        payout_ratio = st.slider("পেআউট অনুপাত (%)", 0, 100, cfg["payout_ratio"])
        market_cap = st.slider("মার্কেট ক্যাপ (সর্বোচ্চ সদস্য)", 1000, 500000, cfg["market_cap_limit"])
        if st.button("💾 Save Settings"):
            new_cfg = {
                "max_levels": max_levels,
                "branching": branching,
                "entry_fee": entry_fee,
                "payout_ratio": payout_ratio,
                "market_cap_limit": market_cap,
                "payout_depth": cfg.get("payout_depth", 3),
            }
            save_config(new_cfg)
            st.success("✅ Settings saved")
            st.rerun()

# ---------- Public registration ----------
st.subheader("🚀 Join the Referral Program")
name = st.text_input("Your name")
ref_code = st.text_input("Referral code (optional)")
if st.button("Join"):
    if not name:
        st.error("Please enter your name.")
    else:
        try:
            member_id, fee, parent_id, level = register_member(ref_code or None)
            checkout_url = start_checkout(entry_fee=fee, member_id=member_id)
            st.markdown(f"[Proceed to payment]({checkout_url})", unsafe_allow_html=True)
            st.info(f"Your member ID: **{member_id}** | Level: {level}")
        except Exception as e:
            st.error(f"Registration failed: {str(e)}")

# ---------- After payment callback ----------
query_params = st.query_params
if "session_id" in query_params and "member" in query_params:
    sess_id = query_params["session_id"]
    mem_id = query_params["member"]
    
    # Validate member ID format
    if mem_id and (mem_id.startswith("N") or mem_id == "A-ROOT"):
        try:
            if verify_and_record(sess_id, mem_id):
                distribute_payouts(mem_id)
                st.success("✅ Payment confirmed! You have been added to the pyramid.")
                # Clear query params
                st.query_params.clear()
                st.rerun()
            else:
                st.error("❌ Payment verification failed.")
        except Exception as e:
            st.error(f"❌ Error processing payment: {str(e)}")
    else:
        st.error("❌ Invalid member ID format.")

# ---------- Dashboard ----------
st.divider()
kpi_cards()
inflow_outflow_chart()
level_bar_chart()
tree_view()
st.divider()
members_table()
