## Setup Instructions

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Stripe API Keys:**
   - Sign up at https://stripe.com and get your test API keys
   - Edit `.streamlit/secrets.toml` and add your keys:
     ```toml
     [stripe]
     secret_key = "sk_test_YOUR_KEY_HERE"
     publishable_key = "pk_test_YOUR_KEY_HERE"
     ```

3. **Configure Owner Credentials:**
   - Edit `.streamlit/secrets.toml` and set owner credentials

4. **Run the application:**
   ```bash
   streamlit run main.py
   ```

## All Fixes Applied

✅ Fixed import syntax error (missing comma)
✅ Updated deprecated Streamlit API calls
✅ Created missing secrets.toml template
✅ Changed Stripe currency from BDT to USD
