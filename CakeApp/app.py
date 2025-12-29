import streamlit as st
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import zipfile
import io
import os
import pandas as pd
import datetime
import extra_streamlit_components as stx
from streamlit_gsheets import GSheetsConnection
import urllib.parse
import re

# --- GOOGLE SHEETS DB SETUP ---

# Constants
# TODO: REPLACE WITH NEW SHEET URL TO AVOID DATA COLLISION
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1GA6TMom4CouSNFEesCEANqe3ZtP2MKk4d9PfsTXmPRQ/edit?gid=0#gid=0"

def get_db_connection():
    return st.connection("gsheets", type=GSheetsConnection)

def get_all_orders():
    conn = get_db_connection()
    try:
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
        expected_cols = ['id', 'date', 'name', 'phone', 'email', 'status', 'payment_status', 'amount', 'details']
        if df.empty or not set(expected_cols).issubset(df.columns):
            return pd.DataFrame(columns=expected_cols)
        df = df.fillna("")
        df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception:
        return pd.DataFrame(columns=['id', 'date', 'name', 'phone', 'email', 'status', 'payment_status', 'amount', 'details'])

def save_order(name, phone, email, amount, details):
    conn = get_db_connection()
    df = get_all_orders()
    
    if not df.empty:
        try:
            current_max = df['id'].max()
            new_id = int(current_max) + 1
        except:
            new_id = 1
    else:
        new_id = 1
        df = pd.DataFrame(columns=['id', 'date', 'name', 'phone', 'email', 'status', 'payment_status', 'amount', 'details'])

    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Clean phone
    if phone:
        phone = re.sub(r'\D', '', str(phone))
    
    new_order = pd.DataFrame([{
        "id": new_id,
        "date": date_str,
        "name": name, 
        "phone": phone,
        "email": email,
        "status": "Order Received",
        "payment_status": "Unpaid",
        "amount": amount,
        "details": str(details)
    }])
    
    updated_df = pd.concat([df, new_order], ignore_index=True)
    conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
    return new_id

def update_status(order_id, new_status, payment_status='Unpaid', new_amount=None):
    conn = get_db_connection()
    df = get_all_orders()
    if not df.empty:
        mask = df['id'] == int(order_id)
        if mask.any():
            df.loc[mask, 'status'] = new_status
            df.loc[mask, 'payment_status'] = payment_status
            if new_amount is not None:
                df.loc[mask, 'amount'] = float(new_amount)
            conn.update(spreadsheet=SPREADSHEET_URL, data=df)

def get_orders_by_phone(phone):
    df = get_all_orders()
    if df.empty: return df
    
    def normalize_phone(p):
        s = str(p).strip()
        if s.endswith('.0'): s = s[:-2]
        return s

    df['phone_clean'] = df['phone'].apply(normalize_phone)
    target_phone = normalize_phone(phone)
    return df[df['phone_clean'] == target_phone].sort_values(by='id', ascending=False)

# --- CONFIGURATION & CONSTANTS ---
ADMIN_PHONE = "918606884320" 
st.set_page_config(page_title="Glaze & Grace Cake Studio", page_icon="🎂", layout="wide")

if 'page' not in st.session_state:
    st.session_state['page'] = 'home'

# Pricing
PRICES = {
    "Vanilla Dream": 400,
    "Rich Chocolate": 500,
    "Red Velvet": 600,
    "Butterscotch": 450,
    "Fresh Fruit": 550
}
SHAPE_PREMIUM = {"Round": 0, "Square": 50, "Heart": 100}
TOPPING_PRICE = 50

# Styles
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&family=Dancing+Script:wght@700&display=swap');
    
    :root {
        --primary: #db2777; /* Pink 600 */
        --primary-light: #f472b6; /* Pink 400 */
        --bg-dark: #1e1b4b; /* Indigo 950 */
        --card-bg: #312e81; /* Indigo 900 */
        --text-light: #fce7f3; /* Pink 100 */
    }
    
    .main { background: var(--bg-dark); color: white; font-family: 'Poppins', sans-serif; }
    
    h1 {
        font-family: 'Dancing Script', cursive;
        background: linear-gradient(to right, #f472b6, #fb7185);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3.5rem !important;
    }
    
    h2, h3, h4 { color: #fbcfe8 !important; }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #db2777 0%, #be185d 100%) !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
    }
    
    /* Inputs */
    .stTextInput input, .stNumberInput input, .stSelectbox, .stTextArea textarea {
        background-color: #fdf2f8 !important; /* Pink 50 */
        color: #831843 !important; /* Pink 900 */
        border-radius: 0.5rem;
    }
    
    /* Card Style */
    [data-testid="stContainer"] {
        background-color: rgba(49, 46, 129, 0.6);
        border: 1px solid #4c1d95;
        border-radius: 1rem;
        padding: 1.5rem;
    }

    /* Track Order Badges */
    .badge-status {
        padding: 0.35rem 0.75rem;
        border-radius: 99px;
        font-weight: 600;
        font-size: 0.75rem;
        color: #4a044e !important; /* Dark Pink Text */
    }
    </style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def calculate_cake_price(flavor, weight, shape, toppings):
    base = PRICES.get(flavor, 400) * weight
    shape_cost = SHAPE_PREMIUM.get(shape, 0)
    toppings_cost = len(toppings) * TOPPING_PRICE
    return base + shape_cost + toppings_cost

def auto_rename_file(uploaded_file, order_id, customer_name):
    clean_name = "".join(x for x in customer_name if x.isalnum())
    ext = os.path.splitext(uploaded_file.name)[1]
    return f"CAKE_{clean_name}_{order_id}{ext}"

def send_email(customer_name, customer_email, order_details, total, comments):
    # Simplified email logic for brevity
    try:
        secrets = st.secrets.get("email", st.secrets)
        # Using same credentials as print app
        msg = MIMEText(f"New Cake Order!\n\nName: {customer_name}\nFlavor: {order_details['flavor']}\nWeight: {order_details['weight']}kg\nTotal: INR {total}")
        msg['Subject'] = f"Cake Order: {customer_name}"
        msg['From'] = secrets["sender_email"]
        msg['To'] = "justinsaju100@gmail.com" # Shop Owner
        
        server = smtplib.SMTP(secrets["smtp_server"], secrets["smtp_port"])
        server.starttls()
        server.login(secrets["sender_email"], secrets["sender_password"])
        server.sendmail(secrets["sender_email"], [secrets["sender_email"], customer_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return False

# --- VIEWS ---

def home_view():
    st.markdown("<div style='text-align:center; padding: 2rem;'><h1>Glaze & Grace 🍰</h1><p style='font-size:1.2rem; color:#fbcfe8;'>Baking happiness, one layer at a time.</p></div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🧁 Menu Highlights")
        for cake, price in PRICES.items():
            st.markdown(f"- **{cake}**: ₹{price}/kg")
    
    with col2:
        st.info("💡 **Special Offer**: Free delivery on orders above 2kg!")
        if st.button("🎂 Order a Cake Now", use_container_width=True):
            st.session_state['page'] = 'order'

def order_view():
    if st.button("← Back"): st.session_state['page'] = 'home'; st.rerun()
    st.title("Design Your Cake 🎨")
    
    with st.form("cake_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Your Name")
            phone = st.text_input("Phone Number")
            email = st.text_input("Email")
        with col2:
            flavor = st.selectbox("Flavor", list(PRICES.keys()))
            weight = st.slider("Weight (kg)", 0.5, 5.0, 1.0, 0.5)
            shape = st.selectbox("Shape", ["Round", "Square", "Heart"])
        
        toppings = st.multiselect("Add-ons (₹50 ea)", ["Choco Chips", "Fresh Fruit", "Macarons", "Gold Leaf", "Sprinkles"])
        message = st.text_input("Message on Cake (e.g. Happy Birthday)")
        ref_image = st.file_uploader("Reference Photo (Optional)", type=['jpg', 'png'])
        
        total = calculate_cake_price(flavor, weight, shape, toppings)
        st.markdown(f"### Total Estimate: ₹{total:.2f}")
        
        if st.form_submit_button("🚀 Place Order"):
            if not name or not phone:
                st.error("Name and Phone are required!")
            else:
                details = {
                    "flavor": flavor, "weight": weight, "shape": shape, 
                    "toppings": toppings, "message": message
                }
                oid = save_order(name, phone, email, total, details)
                
                # Save file if exists
                if ref_image:
                    os.makedirs("orders", exist_ok=True)
                    new_name = auto_rename_file(ref_image, oid, name)
                    with open(os.path.join("orders", new_name), "wb") as f:
                        f.write(ref_image.getbuffer())
                
                send_email(name, email, details, total, message)
                st.success(f"Order #{oid} Placed Successfully!")
                st.balloons()

def track_view():
    st.title("📦 Track Your Cake")
    phone = st.text_input("Enter Phone Number to Track")
    if st.button("Search"):
        df = get_orders_by_phone(phone)
        if df.empty:
            st.warning("No orders found.")
        else:
            for _, row in df.iterrows():
                with st.container():
                    st.subheader(f"Order #{row['id']}")
                    st.write(f"**Status**: {row['status']}")
                    st.write(f"**Amount**: ₹{row['amount']}")
                    
                    if row['payment_status'] == 'Unpaid':
                        st.markdown(f"""
                        <div style='background:#fdf2f8; padding:1rem; border-radius:0.5rem; color:#831843;'>
                            <h4>Unknown Sweetness needs Payment! 🍭</h4>
                            <p>Pay <strong>₹{row['amount']}</strong> via UPI below:</p>
                            <a href="upi://pay?pa=justinsaju21@oksbi&pn=CakeStudio&am={row['amount']}&cu=INR">
                                <button style='background:#db2777; color:white; border:none; padding:0.5rem; border-radius:5px;'>Pay Now</button>
                            </a>
                        </div>
                        """, unsafe_allow_html=True)
                    st.divider()

def admin_view():
    st.title("🔒 Kitchen Dashboard")
    if st.text_input("Admin Password", type="password") == st.secrets["admin_password"]:
        df = get_all_orders()
        edited = st.data_editor(df, num_rows="dynamic", key="editor")
        if st.button("Save Changes"):
            # Update logic simplified for bulk
            for i, row in edited.iterrows():
                # Only update if changed (naive check or just overwrite)
                update_status(row['id'], row['status'], row['payment_status'], row['amount'])
            st.success("Database Updated!")

def terms_view():
    st.title("Terms & Conditions")
    st.write("1. Cakes contain sugar.\n2. No returns after eating half.\n3. Verify design before pickup.")

# --- NAVIGATION ---
def main():
    pages = {
        "🏠 Home": "home", 
        "🎂 Order Cake": "order", 
        "📦 Track": "track", 
        "🔒 Kitchen": "admin",
        "📜 Terms": "terms"
    }
    
    with st.sidebar:
        st.title("Glaze & Grace")
        sel = st.radio("Menu", list(pages.keys()))
        if pages[sel] != st.session_state['page']:
            st.session_state['page'] = pages[sel]
            st.rerun()

    p = st.session_state['page']
    if p == 'home': home_view()
    elif p == 'order': order_view()
    elif p == 'track': track_view()
    elif p == 'admin': admin_view()
    elif p == 'terms': terms_view()

if __name__ == "__main__":
    main()
