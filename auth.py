import streamlit as st

def owner_login():
    """Render a sidebar login form. Returns True if logged in."""
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
                    st.session_state.owner = name
                    st.success("Logged in as owner")
                    st.rerun()
                else:
                    st.error("Invalid credentials")
            except KeyError:
                st.error("⚠️ Secrets not configured. Check .streamlit/secrets.toml")
    return False
