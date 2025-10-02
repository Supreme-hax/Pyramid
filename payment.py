import stripe
import streamlit as st
from db import get_db
from datetime import datetime

try:
    stripe.api_key = st.secrets["stripe"]["secret_key"]
except KeyError:
    st.warning("⚠️ Stripe API key not configured in secrets.toml")
    stripe.api_key = None

def start_checkout(entry_fee: int, member_id: str) -> str:
    """Create a Stripe Checkout session and return its URL."""
    if not stripe.api_key:
        return "#payment-not-configured"
    
    try:
        # Convert BDT to USD (approximate rate: 1 USD ≈ 110 BDT)
        # Stripe doesn't support BDT, so we use USD
        amount_usd = max(1, int(entry_fee / 110))
        
        # Get base URL from Streamlit context
        try:
            base_url = st.get_option("browser.serverAddress")
            if not base_url:
                base_url = "http://localhost:8501"
        except:
            base_url = "http://localhost:8501"
        
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": "Pyramid Entry Fee",
                        "description": f"Member ID: {member_id}"
                    },
                    "unit_amount": amount_usd * 100,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{base_url}/?session_id={{CHECKOUT_SESSION_ID}}&member={member_id}",
            cancel_url=f"{base_url}/?cancel=1",
            metadata={"member_id": member_id}
        )
        return session.url
    except stripe.error.StripeError as e:
        st.error(f"Stripe error: {str(e)}")
        return "#stripe-error"
    except Exception as e:
        st.error(f"Payment setup error: {str(e)}")
        return "#error"

def verify_and_record(session_id: str, member_id: str) -> bool:
    """Verify Stripe payment and record inflow."""
    if not stripe.api_key:
        st.error("Stripe not configured")
        return False
    
    try:
        sess = stripe.checkout.Session.retrieve(session_id)
        
        if sess.payment_status != "paid":
            return False
        
        # Verify member_id matches
        if sess.metadata.get("member_id") != member_id:
            st.error("Member ID mismatch")
            return False
        
        # Check if already recorded
        with get_db() as con:
            existing = con.execute(
                "SELECT id FROM transactions WHERE stripe_session = ?",
                (session_id,)
            ).fetchone()
            
            if existing:
                return True
            
            # Record transaction
            amount = sess.amount_total // 100
            con.execute(
                "INSERT INTO transactions (member_id, type, amount, ts, stripe_session) "
                "VALUES (?,?,?,?,?)",
                (member_id, "inflow", amount,
                 int(datetime.utcnow().timestamp()), session_id),
            )
            
            # Update member as paid
            con.execute(
                "UPDATE members SET paid = ? WHERE id = ?",
                (amount, member_id)
            )
            con.commit()
        
        return True
        
    except stripe.error.StripeError as e:
        st.error(f"Stripe verification error: {str(e)}")
        return False
    except Exception as e:
        st.error(f"Verification error: {str(e)}")
        return False
