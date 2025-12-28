import streamlit as st
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import pandas as pd
import PyPDF2
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
import urllib.parse
import sqlite3
import datetime
import extra_streamlit_components as stx
from streamlit_gsheets import GSheetsConnection

# --- GOOGLE SHEETS DB SETUP ---

# Constants
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1GA6TMom4CouSNFEesCEANqe3ZtP2MKk4d9PfsTXmPRQ/edit?gid=0#gid=0"

def check_secrets():
    # Helper to check if secrets are set up
    if "gsheets" not in st.secrets.get("connections", {}):
        st.error("🚨 Google Sheets Secrets Missing!")
        st.markdown("""
        ### How to Connect Your Database (Google Sheets)
        To save orders, you need to connect this app to your Google Sheet securely.
        
        **Step 1: Get Credentials**
        1. Go to [Google Cloud Console](https://console.cloud.google.com/).
        2. Create a Project > Enable "Google Sheets API".
        3. Create a Service Account > Create Key (JSON).
        4. Download the JSON file.
        
        **Step 2: Share your Sheet**
        1. Open [Your Sheet](https://docs.google.com/spreadsheets/d/1GA6TMom4CouSNFEesCEANqe3ZtP2MKk4d9PfsTXmPRQ/edit).
        2. Click **Share**.
        3. Copy the `client_email` from your JSON file (e.g., `service-account@project.iam.gserviceaccount.com`).
        4. Paste it into Share dialog and give **Editor** access.
        
        **Step 3: Add to Streamlit Secrets**
        Go to your App Dashboard > Settings > Secrets and paste the content of the JSON file under `[connections.gsheets]`.
        """)
        st.stop()
        
def get_db_connection():
    check_secrets()
    return st.connection("gsheets", type=GSheetsConnection)

def get_all_orders():
    conn = get_db_connection()
    try:
        # ttl=0 ensures we fetch the latest data every time
        df = conn.read(spreadsheet=SPREADSHEET_URL, ttl=0)
        # Ensure columns exist if sheet is empty
        expected_cols = ['id', 'date', 'name', 'phone', 'email', 'status', 'payment_status', 'amount', 'details']
        if df.empty or not set(expected_cols).issubset(df.columns):
            # Return empty DF with correct structure if fresh
            return pd.DataFrame(columns=expected_cols)
        
        # Handle Potential NaN for cleaner UI
        df = df.fillna("")
        # Force ID to be numeric if possible
        df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        # Fallback/Error logging
        # st.error(f"DB Error: {e}")
        return pd.DataFrame(columns=['id', 'date', 'name', 'phone', 'email', 'status', 'payment_status', 'amount', 'details'])

def save_order(name, phone, email, amount, details):
    conn = get_db_connection()
    df = get_all_orders()
    
    # Generate New ID
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

    # Clean phone strictly before saving
    import re
    if phone:
        phone = re.sub(r'\D', '', str(phone))
        # If user typed 12 digits starting with 91, keep it. 
        # If 10, keep it.
        # But for 'clean' DB, 10 digits is preferred if local.
        # Let's just save valid digits.
    
    new_order = pd.DataFrame([{
        "id": new_id,
        "date": date_str,
        "name": name, 
        "phone": phone,
        "email": email,
        "status": "Pending",
        "payment_status": "Unpaid",
        "amount": amount,
        "details": str(details)
    }])
    
    updated_df = pd.concat([df, new_order], ignore_index=True)
    
    # Write back to Sheet
    conn.update(spreadsheet=SPREADSHEET_URL, data=updated_df)
    
    return new_id

def update_status(order_id, new_status, payment_status='Unpaid'):
    conn = get_db_connection()
    df = get_all_orders()
    
    if not df.empty:
        # Find row with this ID
        mask = df['id'] == int(order_id)
        if mask.any():
            df.loc[mask, 'status'] = new_status
            df.loc[mask, 'payment_status'] = payment_status
            conn.update(spreadsheet=SPREADSHEET_URL, data=df)

def get_orders_by_phone(phone):
    df = get_all_orders()
    if df.empty: return df
    
    # String match phone
    # Clean both sides to ensure matching (strip spaces, casting)
    # df['phone'] might be int, float, or str in sheets.
    # Convert to string, remove '.0' if float, strip spaces.
    
    def normalize_phone(p):
        s = str(p).strip()
        if s.endswith('.0'): s = s[:-2]
        return s

    df['phone_clean'] = df['phone'].apply(normalize_phone)
    target_phone = normalize_phone(phone)
    
    # Filter using normalized strings
    filtered = df[df['phone_clean'] == target_phone].sort_values(by='id', ascending=False)
    
    # Clean up temp column before returning? Not strictly necessary but cleaner.
    # Filtered view:
    return filtered

def init_db():
    # Deprecated/No-op for Sheets, but kept for main() compatibility
    pass

# --- CONFIGURATION & STYLING ---
st.set_page_config(
    page_title="Professional Print Services",
    page_icon="🖨️",
    layout="wide"
)

# Initialize Session State
if 'page' not in st.session_state:
    st.session_state['page'] = 'home'

# Cookie Manager for Persistence
cookie_manager = stx.CookieManager(key="cookie_manager")

# Pricing Constants
PRICE_BW = 2.0
PRICE_COLOR = 10.0
PRICE_GLOSSY_ADDON = 20.0 # Assuming this is flat rate or per page substitute? The user said "and 20 rupees for glossy paper". I'll treat it as a per-page price for glossy paper prints. 
# Re-reading prompt: "10 rupees for colour, 2 rupees for black and white, and 20 rupees for glossy paper"
# I will interpret this as:
# B&W Standard: 2
# Color Standard: 10
# Any Glossy: 20 (Simpler interpretation, or maybe Glossy is just for color? I'll add it as a 'Paper Type' option that overrides color price or is a distinct category).
# Let's stick to the prompt's specific items as base prices.

st.markdown("""
    <style>
    /* ===== IMPORTS ===== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Poppins:wght@600;700;800&display=swap');
    
    /* ===== GLOBAL DESIGN TOKENS ===== */
    :root {
        --color-primary: #4f46e5;
        --color-primary-dark: #4338ca;
        --color-primary-light: #6366f1;
        --color-secondary: #06b6d4;
        --color-success: #10b981;
        --color-warning: #f59e0b;
        --color-error: #ef4444;
        --color-bg-main: #0f172a;
        --color-bg-card: #1e293b;
        --color-text-primary: #f8fafc;
        --color-text-secondary: #94a3b8;
        --color-border: #334155;
        --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        --radius-sm: 0.375rem;
        --radius-md: 0.5rem;
        --radius-lg: 0.75rem;
        --radius-xl: 1rem;
        --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
        --transition-base: 200ms cubic-bezier(0.4, 0, 0.2, 1);
        --transition-slow: 300ms cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    /* ===== GLOBAL RESETS ===== */
    .main {
        background: #0f172a;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    /* ===== TYPOGRAPHY ===== */
    h1, h2, h3, h4, h5, h6, label, p, span, div {
        font-family: 'Inter', sans-serif;
    }

    /* Force high contrast for labels and headers */
    label p, .stMarkdown p, h1, h2, h3, h4 {
        color: #f8fafc !important;
    }
    
    h1 {
        font-family: 'Poppins', sans-serif;
        font-size: 2.5rem;
        background: linear-gradient(135deg, var(--color-primary-light) 0%, var(--color-secondary) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 1rem;
    }
    
    /* ===== INPUTS ===== */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input,
    .stSelectbox > div > div > select,
    .stTextArea > div > div > textarea {
        border: 2px solid var(--color-border);
        border-radius: var(--radius-md);
        padding: 0.75rem 1rem;
        font-family: 'Inter', sans-serif;
        transition: all var(--transition-fast);
        background: #ffffff !important;
        color: #1e293b !important;
        font-weight: 500;
    }

    /* Fix Placeholder Contrast on White Background */
    ::placeholder {
        color: #64748b !important;
        opacity: 1 !important;
    }
    
    .stTextInput > div > div > input:focus,
    .stNumberInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: var(--color-primary-light);
        box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        outline: none;
    }

    div[data-baseweb="select"] > div {
        background-color: white !important;
        color: #1e293b !important;
    }
    
    /* ===== CONTAINERS & CARDS ===== */
    [data-testid="stContainer"] {
        background: #1e293b;
        border-radius: var(--radius-xl);
        padding: 1.5rem;
        box-shadow: var(--shadow-md);
        border: 1px solid #334155;
    }
    
    [data-testid="stContainer"]:hover {
        box-shadow: var(--shadow-lg);
        border-color: var(--color-primary-light);
    }
    
    /* ===== EXPANDERS ===== */
    .streamlit-expanderHeader {
        background: linear-gradient(135deg, var(--color-bg-card) 0%, #fafbfc 100%);
        border-radius: var(--radius-md);
        padding: 1rem 1.5rem;
        font-weight: 600;
        color: var(--color-text-primary);
        border: 1px solid var(--color-border);
        transition: all var(--transition-fast);
    }
    
    .streamlit-expanderHeader:hover {
        background: linear-gradient(135deg, #fafbfc 0%, var(--color-bg-card) 100%);
        border-color: var(--color-primary);
    }
    
    /* ===== FILE UPLOADER ===== */
    [data-testid="stFileUploader"] {
        background: linear-gradient(135deg, #f8fafc 0%, #ffffff 100%);
        border: 2px dashed var(--color-border);
        border-radius: var(--radius-lg);
        padding: 2rem;
        transition: all var(--transition-base);
    }
    
    [data-testid="stFileUploader"]:hover {
        border-color: var(--color-primary);
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    }
    
    /* ===== DATA EDITOR / TABLE ===== */
    [data-testid="stDataFrame"] {
        border-radius: var(--radius-lg);
        overflow: hidden;
        box-shadow: var(--shadow-md);
    }
    
    /* ===== ALERTS & MESSAGES ===== */
    .stSuccess, .stInfo, .stWarning, .stError {
        border-radius: var(--radius-md);
        padding: 1rem 1.5rem;
        border-left-width: 4px;
        box-shadow: var(--shadow-sm);
    }
    
    .stSuccess {
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
        border-left-color: var(--color-success);
    }
    
    .stInfo {
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        border-left-color: var(--color-primary);
    }
    
    .stWarning {
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
        border-left-color: var(--color-warning);
    }
    
    .stError {
        background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
        border-left-color: var(--color-error);
    }
    
    /* ===== SIDEBAR ===== */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
        padding-top: 2rem;
    }
    
    [data-testid="stSidebar"] .stRadio > label {
        color: #e2e8f0;
        font-weight: 500;
        padding: 0.75rem 1rem;
        border-radius: var(--radius-md);
        transition: all var(--transition-fast);
        margin-bottom: 0.5rem;
        display: block;
    }
    
    [data-testid="stSidebar"] .stRadio > label:hover {
        background: rgba(255, 255, 255, 0.1);
    }
    
    /* ===== CUSTOM UTILITY CLASSES ===== */
    .gradient-border {
        position: relative;
        background: var(--color-bg-card);
        border-radius: var(--radius-xl);
        padding: 2px;
        background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%);
    }
    
    .gradient-border > div {
        background: var(--color-bg-card);
        border-radius: calc(var(--radius-xl) - 2px);
        padding: 1.5rem;
    }
    
    /* ===== ANIMATIONS ===== */
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes pulse {
        0%, 100% {
            opacity: 1;
        }
        50% {
            opacity: 0.8;
        }
    }
    
    .animate-fade-in {
        animation: fadeInUp 0.6s ease-out;
    }
    
    /* ===== LOADING STATES ===== */
    .stSpinner > div {
        border-color: var(--color-primary);
        border-right-color: transparent;
    }
    
    /* ===== DIVIDERS ===== */
    hr {
        margin: 2rem 0;
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent 0%, var(--color-border) 50%, transparent 100%);
    }
    </style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---

def navigate_to(page):
    st.session_state['page'] = page
    st.rerun()

def calculate_price(pages, color_mode, paper_type):
    rate = 0
    # Logic based on prompt:
    # 2 for B&W
    # 10 for Color
    # 20 for Glossy (Assuming Glossy overwrites others or is a premium paper)
    
    if paper_type == "Glossy":
        rate = 20
    elif color_mode == "Full Color":
        rate = 10
    else: # Black & White
        rate = 2
    
    return pages * rate

    return pages * rate

@st.cache_data
def count_pages(uploaded_files):
    total_pages = 0
    file_details = []
    
    for uploaded_file in uploaded_files:
        try:
            if uploaded_file.type == "application/pdf":
                pdf_reader = PyPDF2.PdfReader(uploaded_file)
                num_pages = len(pdf_reader.pages)
                total_pages += num_pages
                file_details.append(f"{uploaded_file.name}: {num_pages} pages")
            else:
                # Images or others count as 1
                total_pages += 1
                file_details.append(f"{uploaded_file.name}: 1 page (Image/Doc)")
        except Exception as e:
            file_details.append(f"{uploaded_file.name}: Error counting")
            
    return total_pages, file_details

def auto_rename_file(uploaded_file, order_id, customer_name):
    # Format: Name_Date_OrderID.ext
    # Sanitize name
    safe_name = "".join(x for x in customer_name if x.isalnum())
    date_str = datetime.datetime.now().strftime("%d%b") # e.g. 28Dec
    ext = os.path.splitext(uploaded_file.name)[1]
    
    new_name = f"{safe_name}_{date_str}_Order{order_id}{ext}"
    uploaded_file.name = new_name # Streamlit allows modifying this attribute
    return uploaded_file

def generate_receipt(customer_name, order_details, total_cost, file_breakdown):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Header
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 50, "Print Service Receipt")
    
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Customer: {customer_name}")
    c.drawString(50, height - 100, f"Date: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Order Details
    c.drawString(50, height - 140, "Order Details:")
    c.line(50, height - 145, 250, height - 145)
    
    y = height - 165
    c.drawString(60, y, f"Pages: {order_details['pages']}")
    y -= 20
    c.drawString(60, y, f"Color: {order_details['color']}")
    y -= 20
    c.drawString(60, y, f"Paper: {order_details['paper']}")
    y -= 20
    c.drawString(60, y, f"Sides: {order_details['sides']}")
    
    # Files
    y -= 40
    c.drawString(50, y, "Files:")
    for f in file_breakdown:
        y -= 20
        c.drawString(60, y, f"- {f}")
        
    # Total
    y -= 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, f"Total Amount: INR {total_cost:.2f}")
    
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

def send_email(customer_name, customer_email, customer_phone, order_details, uploaded_files, comments, total_cost, file_breakdown):
    try:
        smtp_server = st.secrets["smtp_server"]
        smtp_port = st.secrets["smtp_port"]
        sender_email = st.secrets["sender_email"]
        sender_password = st.secrets["sender_password"]
        receiver_email = "justinsaju100@gmail.com"  # Updated shop owner email
    except Exception:
        # Development mode fallback
        return False, "SMTP Configuration missing."

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Cc'] = customer_email # Add CC header
    msg['Subject'] = f"Print Order: {customer_name}"

    # Format file breakdown for email
    files_str = "\n".join([f"    - {f}" for f in file_breakdown])

    body = f"""
    New Print Order
    ===============
    
    Customer Details:
    -----------------
    Name: {customer_name}
    Phone: {customer_phone}
    Email: {customer_email}
    
    Order Specifications:
    ---------------------
    Color Mode: {order_details['color']}
    Paper Type: {order_details['paper']}
    Sides: {order_details['sides']}
    
    File Summary:
    -------------
{files_str}
    
    Total Pages: {order_details['pages']}
    
    -----------------------------------
    Total Estimated Cost: ₹{total_cost}
    -----------------------------------
    
    Additional Comments:
    {comments}
    """
    msg.attach(MIMEText(body, 'plain'))

    # Attach files
    for uploaded_file in uploaded_files:
        try:
            uploaded_file.seek(0)
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(uploaded_file.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {uploaded_file.name}',
            )
            msg.attach(part)
        except Exception as e:
            return False, f"Error attaching {uploaded_file.name}: {e}"

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        
        # Send to both Shop Owner AND Customer
        recipients = [receiver_email, customer_email]
        server.sendmail(sender_email, recipients, text)
        
        server.quit()
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)


# --- VIEWS ---

def home_view():
    # Hero Section
    st.markdown("""
    <div style='text-align: center; padding: 3rem 1rem; background: linear-gradient(135deg, rgba(79, 70, 229, 0.05) 0%, rgba(6, 182, 212, 0.05) 100%); border-radius: 1rem; margin-bottom: 2rem;'>
        <h1 style='font-size: 3rem; margin-bottom: 0.5rem;'>Professional Print Services 🖨️</h1>
        <p style='font-size: 1.25rem; color: #64748b; max-width: 600px; margin: 0 auto;'>
            High-quality printing at unbeatable prices. Upload, order, and track your prints seamlessly.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # --- HOW IT WORKS SECTION ---
    st.markdown("### 🚀 How It Works")
    
    cols = st.columns(4)
    steps = [
        {"icon": "📤", "title": "Upload", "desc": "Upload your PDF/Docs securely"},
        {"icon": "💰", "title": "Quote", "desc": "Get instant price estimate"},
        {"icon": "✅", "title": "Order", "desc": "Submit & Track online"},
        {"icon": "📦", "title": "Collect", "desc": "Pay via QR & Pickup"}
    ]
    
    for col, step in zip(cols, steps):
        with col:
            st.markdown(f"""
            <div style='text-align: center; padding: 1.5rem; background: white; border-radius: 0.75rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: all 0.3s; border: 1px solid #e2e8f0;'>
                <div style='font-size: 3rem; margin-bottom: 0.5rem;'>{step['icon']}</div>
                <h4 style='color: #4f46e5; margin-bottom: 0.5rem;'>{step['title']}</h4>
                <p style='font-size: 0.875rem; color: #64748b; margin: 0;'>{step['desc']}</p>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    
    # Symmetrical 2-column layout
    col1, col2 = st.columns(2, gap="large")
    
    # Left Column: Pricing with gradient border
    with col1:
        st.markdown("### 🏷️ Pricing Info")
        with st.container(border=True):
            st.markdown("""
            <div style='background: linear-gradient(135deg, #f8fafc 0%, #ffffff 100%); padding: 1rem; border-radius: 0.5rem;'>
                <h4 style='color: #4f46e5; margin-bottom: 1rem;'>Standard Rates</h4>
                <div style='margin-bottom: 1rem;'>
                    <span style='font-size: 1.5rem; font-weight: 700; color: #10b981;'>₹2</span>
                    <span style='color: #64748b;'> / page</span>
                    <div style='color: #64748b; font-size: 0.875rem;'>Black & White</div>
                </div>
                <div style='margin-bottom: 1rem;'>
                    <span style='font-size: 1.5rem; font-weight: 700; color: #06b6d4;'>₹10</span>
                    <span style='color: #64748b;'> / page</span>
                    <div style='color: #64748b; font-size: 0.875rem;'>Full Color</div>
                </div>
                <div style='background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); padding: 0.75rem; border-radius: 0.5rem; border-left: 4px solid #f59e0b;'>
                    <div style='font-weight: 600; color: #92400e; margin-bottom: 0.25rem;'>✨ Premium</div>
                    <span style='font-size: 1.5rem; font-weight: 700; color: #92400e;'>₹20</span>
                    <span style='color: #92400e;'> / page</span>
                    <div style='color: #92400e; font-size: 0.875rem;'>Glossy Paper</div>
                </div>
                <p style='font-size: 0.75rem; color: #94a3b8; margin-top: 1rem; margin-bottom: 0;'>*Prices may vary for bulk orders.</p>
            </div>
            """, unsafe_allow_html=True)
        
    # Right Column: Calculator
    with col2:
        st.markdown("### 🧮 Quick Cost Calculator")
        with st.container(border=True):
            calc_pages = st.number_input("Number of Pages", min_value=1, value=10, key="calc_pages")
            calc_color = st.selectbox("Color Mode", ["Black & White", "Full Color"], key="calc_color")
            calc_paper = st.selectbox("Paper Type", ["Standard", "Glossy"], key="calc_paper")
            
            p_price = "Glossy" if calc_paper == "Glossy" else "Standard" 
            est = calculate_price(calc_pages, calc_color, p_price)
            
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #4f46e5 0%, #06b6d4 100%); color: white; padding: 1.5rem; border-radius: 0.75rem; text-align: center; margin-top: 1rem;'>
                <div style='font-size: 0.875rem; opacity: 0.9; margin-bottom: 0.25rem;'>Estimated Total</div>
                <div style='font-size: 2.5rem; font-weight: 700;'>₹{est:.2f}</div>
            </div>
            """, unsafe_allow_html=True)
            
    st.write("")
    
    # Call to Action
    col_spacer1, col_cta, col_spacer2 = st.columns([1, 2, 1])
    with col_cta:
        if st.button("🚀 Start Your Order", type="primary", use_container_width=True):
            navigate_to('order')



def order_view():
    if st.button("← Back to Home"):
        navigate_to('home')
        
    st.title("Submit Your Order")
    
    # --- 1. Customer Details ---
    st.subheader("1. Contact Details")
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full Name")
            phone_raw = st.text_input("Mobile Number (10 digits)", placeholder="9876543210")
            # Auto-clean input immediately (remove spaces/dashes)
            if phone_raw:
                # Keep only digits
                import re
                phone = re.sub(r'\D', '', phone_raw)
            else:
                phone = ""
                
            if phone and len(phone) != 10:
                st.error("Please enter a valid 10-digit mobile number.")
        with col2:
            email = st.text_input("Email Address", placeholder="name@example.com")

    # --- 2. Upload (Reactive) ---
    st.subheader("2. Document Upload")
    with st.container(border=True):
        uploaded_files = st.file_uploader(
            "Upload your files (PDF, JPG, PNG)", 
            type=['pdf', 'jpg', 'png'], 
            accept_multiple_files=True
        )
        
        # Live Page Counting
        detected_pages = 0
        file_info = []
        if uploaded_files:
            detected_pages, file_info = count_pages(uploaded_files)
            st.info(f"Detected {len(uploaded_files)} file(s) with approx {detected_pages} pages.")
            with st.expander("See file details"):
                for f in file_info:
                    st.write(f"- {f}")


    # --- 3. Preferences (Reactive) ---
    st.subheader("3. Print Preferences")
    with st.container(border=True):
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            color_mode = st.selectbox("Color Mode", ["Black & White", "Full Color"])
        with col_b:
            paper_type = st.selectbox("Paper Type", ["Standard", "Glossy"])
        with col_c:
            sides = st.selectbox("Sides", ["Single-sided", "Double-sided"])
            
        comments = st.text_area("Additional Comments", placeholder="Spiral binding, specific instructions, etc.")

    # --- 4. Live Price Quote ---
    st.divider()
    price_logic_paper = "Glossy" if paper_type == "Glossy" else "Standard"
    estimated_total = calculate_price(detected_pages, color_mode, price_logic_paper)
    
    # Highlight the price
    st.markdown(f"""
    <div style="text-align: center; padding: 20px; background-color: #e8f5e9; border-radius: 10px; border: 2px solid #4caf50;">
        <h2 style="color: #2e7d32; margin:0;">Total Estimated Cost: ₹{estimated_total:.2f}</h2>
        <p style="margin:0; color: #555;">({detected_pages} pages @ {color_mode} / {paper_type})</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.write("") # Spacer

    # --- 5. Submit Action ---
    st.write("")
    agree_terms = st.checkbox("I agree to the Terms of Service and confirm I have the rights to print this document")
    
    submit_order = st.button("Confirm & Send Order", type="primary", use_container_width=True)
    
    if submit_order:
        missing = []
        if not name: missing.append("Name")
        if not phone: missing.append("Phone")
        if not uploaded_files: missing.append("Files")
        if not agree_terms: missing.append("Terms of Service Agreement")
        
        if missing:
            st.error(f"Please provide: {', '.join(missing)}")
        else:
            with st.spinner("Processing Order..."):
                # 0. Init DB (Safe to call repeatedly)
                init_db()
                
                # 1. Save to Database to get Order ID
                order_data = {
                    "color": color_mode,
                    "paper": paper_type,
                    "sides": sides,
                    "pages": detected_pages
                }
                order_id = save_order(name, phone, email, estimated_total, order_data)
                
                # 2. Rename Files
                renamed_files = []
                for f in uploaded_files:
                    renamed_files.append(auto_rename_file(f, order_id, name))
                
                # 3. Send Email (with renamed files)
                success, msg = send_email(name, email, phone, order_data, renamed_files, comments, estimated_total, file_info)
                
                if success:
                    st.success(f"Order #{order_id} Sent Successfully!")
                    st.balloons()
                    
                    # 1. Generate Receipt
                    pdf_buffer = generate_receipt(name, order_data, estimated_total, file_info)
                    
                    # 2. WhatsApp Link (Now using Real Order ID)
                    wa_message = urllib.parse.quote(f"Hi, I just placed Order #{order_id}. Name: {name}. Please confirm.")
                    wa_link = f"https://wa.me/918606884320?text={wa_message}" 
                    
                    st.markdown(f"""
                    <div style="background-color: #e3f2fd; padding: 20px; border-radius: 10px; text-align: center; border-left: 5px solid #2196f3;">
                        <h3 style="color: #0d47a1; margin-top: 0;">Order #{order_id} Received! ✅</h3>
                        <p style="font-size: 1.1em;">We have received your order details.</p>
                        <p style="font-size: 1.1em; font-weight: bold; color: #d32f2f;">
                            ⚠️ PLEASE WAIT for a confirmation message on WhatsApp before making the payment.
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Action Buttons
                    st.write("")
                    col_wa, col_dl = st.columns(2)
                    with col_wa:
                        st.link_button("💬 Track Status on WhatsApp", wa_link, type="primary", use_container_width=True)
                    with col_dl:
                        st.download_button(
                            label="📄 Download Receipt",
                            data=pdf_buffer,
                            file_name=f"receipt_{name.replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )

                else:
                    if "SMTP" in msg or "missing" in msg: 
                         st.warning("Order Processed (Demo Mode)")
                         st.write(f"Email would be sent to shop owner. Setup secrets.toml to enable real sending.")
                         st.error(f"System Message: {msg}")
                    else:
                        st.error(f"Failed to send: {msg}")

def admin_view():
    st.title("Admin Dashboard 🔒")
    
    # Simple Sidebar Login
    with st.sidebar:
        st.header("Login")
        pwd = st.text_input("Password", type="password")
        # Secure Password Check (Must be set in secrets.toml)
        correct_password = st.secrets.get("admin_password")
        
        if correct_password and pwd == correct_password: 
            st.session_state['admin_logged_in'] = True
        elif pwd:
            st.error("Invalid Password")
            
    if not st.session_state.get('admin_logged_in'):
        st.warning("Please log in from the sidebar to access the admin panel.")
        return

    st.success("Logged in as Admin")
    
    # --- Data Editor ---
    st.subheader("Order Management")
    
    df = get_all_orders()
    
    # Ensure payment_status exists in DF (fallback for old DBs read without migration in pure pandas read)
    if 'payment_status' not in df.columns:
        df['payment_status'] = 'Unpaid'

    def make_wa_link(row):

        # Contextual Payment Message
        if row['status'] == 'Waiting for Payment' and row['payment_status'] == 'Unpaid':
             payment_msg = f"Please proceed to pay ₹{row['amount']:.2f}. Go to 'Track Orders' on our site to view the QR Code."
        elif row['payment_status'] == 'Unpaid':
            payment_msg = f"Amt: ₹{row['amount']:.2f}. Payment Pending."
        elif row['payment_status'] == 'Paid':
             payment_msg = "Payment Received. Thank you!"
        
        msg = urllib.parse.quote(f"Hi {row['name']}, your Order #{row['id']} is {row['status']}! {payment_msg}")
        
        
        # Robust Phone Cleaning for Google Sheets Floats (e.g. 9998887777.0)
        p_str = str(row['phone']).strip()
        if p_str.endswith(".0"): 
             p_str = p_str[:-2] # Remote the .0 part first
        
        # Now remove non-digits
        import re
        p_digits = re.sub(r'\D', '', p_str)
        
        # Logic for India (+91)
        if len(p_digits) == 10:
            final_phone = "91" + p_digits
        elif len(p_digits) == 12 and p_digits.startswith("91"):
            final_phone = p_digits
        else:
            # Fallback for weird lengths: If 11 digits starting with 0? Remove 0.
            if len(p_digits) == 11 and p_digits.startswith("0"):
                 final_phone = "91" + p_digits[1:]
            else:
                 final_phone = "91" + p_digits 

        return f"https://wa.me/{final_phone}?text={msg}"

    if not df.empty:
        df['notify_link'] = df.apply(make_wa_link, axis=1)

        edited_df = st.data_editor(
            df,
            column_config={
                "notify_link": st.column_config.LinkColumn(
                    "Notify Customer",
                    help="Click to open WhatsApp",
                    display_text="Open WhatsApp 💬"
                ),
                "status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["Pending", "Waiting for Payment", "Printing", "Ready for Pickup", "Completed"],
                    required=True
                ),
                "payment_status": st.column_config.SelectboxColumn(
                    "Payment",
                    options=["Unpaid", "Paid", "Refunded"],
                    required=True
                )
            },
            disabled=["id", "date", "name", "phone", "email", "amount", "details", "notify_link"],
            hide_index=True,
            key="order_editor"
        )
        
        if st.button("Save Changes"):
            for index, row in edited_df.iterrows():
                update_status(row['id'], row['status'], row['payment_status'])
            st.success("Database Updated!")
            st.rerun()
            
    else:
        st.info("No orders found in database.")

def track_orders_view():
    # Header with search-focused design
    st.markdown("""
    <div style='text-align: center; margin-bottom: 2rem;'>
        <h1>Track My Orders 📦</h1>
        <p style='color: #64748b; font-size: 1.1rem;'>Enter your phone number to view all your orders and their current status</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 1. Try to get phone from Cookie
    cookie_phone = cookie_manager.get(cookie="user_phone")
    
    # 2. Search Box with better styling
    col_spacer1, col_search, col_spacer2 = st.columns([1, 2, 1])
    with col_search:
        phone_input = st.text_input(
            "📱 Phone Number", 
            value=cookie_phone if cookie_phone else "", 
            placeholder="Enter 10-digit phone number",
            label_visibility="collapsed"
        )
    
    if st.button("🔍 Track Orders", type="primary", use_container_width=False) or phone_input:
        if phone_input:
            # Save to cookie for future
            cookie_manager.set("user_phone", phone_input, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
            
            orders = get_orders_by_phone(phone_input)
            
            if not orders.empty:
                st.markdown(f"""
                <div style='background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%); padding: 1rem; border-radius: 0.75rem; border-left: 4px solid #10b981; margin-bottom: 1.5rem;'>
                    <strong style='color: #065f46;'>✅ Found {len(orders)} order(s) for {phone_input}</strong>
                </div>
                """, unsafe_allow_html=True)
                
                for index, row in orders.iterrows():
                    # Status color mapping
                    status_colors = {
                        'Pending': ('#f59e0b', '#fffbeb', 'Pending'),
                        'Waiting for Payment': ('#3b82f6', '#eff6ff', 'Awaiting Payment'),
                        'Printing': ('#8b5cf6', '#f5f3ff', 'In Progress'),
                        'Ready for Pickup': ('#10b981', '#ecfdf5', 'Ready'),
                        'Completed': ('#6b7280', '#f9fafb', 'Completed')
                    }
                    
                    status = row['status']
                    color, bg, label = status_colors.get(status, ('#6b7280', '#f9fafb', status))
                    
                    # Payment status colors
                    pay_status = row.get('payment_status', 'Unpaid')
                    pay_color = '#10b981' if pay_status == 'Paid' else '#ef4444'
                    pay_bg = '#ecfdf5' if pay_status == 'Paid' else '#fef2f2'
                    
                    with st.container(border=True):
                        # Order header
                        st.markdown(f"""
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; padding-bottom: 0.75rem; border-bottom: 1px solid #e2e8f0;'>
                            <div>
                                <h3 style='margin: 0; color: #1e293b;'>Order #{row['id']}</h3>
                                <p style='margin: 0.25rem 0 0 0; color: #64748b; font-size: 0.875rem;'>{row['date']}</p>
                            </div>
                            <div style='text-align: right;'>
                                <div style='background: {bg}; color: {color}; padding: 0.5rem 1rem; border-radius: 9999px; font-weight: 600; font-size: 0.875rem; display: inline-block; margin-bottom: 0.5rem;'>
                                    {label}
                                </div>
                                <div style='background: {pay_bg}; color: {pay_color}; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: 600; font-size: 0.75rem; display: inline-block;'>
                                    {pay_status}
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Order details
                        col_details, col_amount = st.columns([3, 1])
                        with col_details:
                            st.markdown(f"**Details:** {row['details']}")
                        with col_amount:
                            st.markdown(f"""
                            <div style='text-align: right;'>
                                <div style='font-size: 0.875rem; color: #64748b;'>Amount</div>
                                <div style='font-size: 1.5rem; font-weight: 700; color: #1e293b;'>₹{row['amount']:.2f}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        # Show Payment QR if Waiting for Payment
                        if row['status'] == "Waiting for Payment" and row.get('payment_status', 'Unpaid') == 'Unpaid':
                            with st.expander("💸 Pay Now (QR Code)", expanded=False):
                                col_qr, col_inst = st.columns([1, 1])
                                with col_qr:
                                    st.image("assets/qr_code.png", width=200)
                                with col_inst:
                                    st.markdown(f"""
                                    <div style='background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #3b82f6;'>
                                        <h4 style='margin-top: 0; color: #1e40af;'>Payment Instructions</h4>
                                        <p style='color: #1e40af; margin-bottom: 0.5rem;'><strong>Amount: ₹{row['amount']:.2f}</strong></p>
                                        <ol style='color: #1e40af; margin: 0; padding-left: 1.25rem; font-size: 0.875rem;'>
                                            <li>Scan the QR code</li>
                                            <li>Complete payment</li>
                                            <li>Wait for status update</li>
                                        </ol>
                                    </div>
                                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style='background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); padding: 1.5rem; border-radius: 0.75rem; border-left: 4px solid #f59e0b; text-align: center;'>
                    <strong style='color: #92400e;'>⚠️ No orders found for this number</strong>
                    <p style='color: #92400e; margin-top: 0.5rem; margin-bottom: 0;'>Please check the phone number or place a new order.</p>
                </div>
                """, unsafe_allow_html=True)
                
            # Contact Admin Option
            st.divider()
            st.markdown("### Need Help?")
            help_msg = urllib.parse.quote(f"Hi, I need help with my orders for phone {phone_input}.")
            st.link_button("💬 Contact Shop Owner on WhatsApp", f"https://wa.me/918606884320?text={help_msg}", use_container_width=True)
            
        else:
            st.error("Please enter a phone number.")


# --- MAIN CONTROLLER ---

def main():
    # Sidebar Navigation
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/3142/3142200.png", width=100) # Placeholder generic print icon
        st.title("Print Service")
        
        # Mapping generic names to internal IDs
        NAV_MAP = {
            "🏠 Home": "home",
            "📄 Order Now": "order",
            "📦 Track Orders": "track",
            "🔒 Admin Panel": "admin"
        }
        
        # Reverse map for display
        REV_NAV_MAP = {v: k for k, v in NAV_MAP.items()}
        
        # Current selection based on state
        current_nav = REV_NAV_MAP.get(st.session_state.get('page', 'home'), "🏠 Home")
        
        selected_page = st.radio(
            "Navigation", 
            list(NAV_MAP.keys()), 
            index=list(NAV_MAP.keys()).index(current_nav),
            label_visibility="collapsed"
        )
        
        # Update state if changed
        if NAV_MAP[selected_page] != st.session_state['page']:
            st.session_state['page'] = NAV_MAP[selected_page]
            st.rerun()

        st.divider()
        st.info("📞 Help: +91 8606884320")

    if st.session_state['page'] == 'home':
        home_view()
    elif st.session_state['page'] == 'order':
        order_view()
    elif st.session_state['page'] == 'admin':
        admin_view()
    elif st.session_state['page'] == 'track':
        track_orders_view()

if __name__ == "__main__":
    init_db() # Ensure DB/Table exists on startup
    main()
