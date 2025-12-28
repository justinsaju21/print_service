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
    /* Global Settings */
    .main {
        background-color: #f8f9fa;
    }
    h1 {
        color: #1a237e;
        font-family: 'Roboto', 'Helvetica Neue', sans-serif;
        text-align: center;
        font-weight: 700;
        margin-bottom: 30px;
    }
    h2, h3 {
        color: #283593;
        font-family: 'Roboto', sans-serif;
    }
    
    /* Price Card Styling Removed (Using Native Containers) */
    
    /* Button Styling */
    .stButton>button {
        background: linear-gradient(45deg, #1565c0, #42a5f5);
        color: white;
        border: none;
        border-radius: 25px;
        height: 55px;
        font-weight: 600;
        font-size: 1.1rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.15);
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background: linear-gradient(45deg, #0d47a1, #1e88e5);
        box-shadow: 0 6px 8px rgba(0,0,0,0.2);
        transform: scale(1.02);
    }
    
    /* Input Fields */
    .stTextInput>div>div>input {
        border-radius: 10px;
        border: 1px solid #ccc;
        padding: 10px;
    }
    
    /* Success/Price Box */
    .metric-box {
        text-align: center;
        padding: 20px;
        background: white;
        border-radius: 12px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
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
    st.title("Professional Print Services")
    st.markdown("### High Quality Printing at Unbeatable Prices")
    
    # Symmetrical 2-column layout
    col1, col2 = st.columns(2, gap="large")
    
    # Left Column: Pricing
    with col1:
        st.subheader("Pricing Info")
        with st.container(border=True):
            st.markdown("""
            ### 🏷️ Standard Rates
            - **Black & White:** ₹2 per page
            - **Full Color:** ₹10 per page
            
            ### ✨ Premium
            - **Glossy Paper:** ₹20 per page
            
            <small style="color: grey;">*Prices may vary for bulk orders.</small>
            """, unsafe_allow_html=True)
        
    # Right Column: Calculator (Moved here for balance)
    with col2:
        st.subheader("Quick Cost Calculator")
        with st.container(border=True):
            calc_pages = st.number_input("Number of Pages", min_value=1, value=10)
            calc_color = st.selectbox("Color Mode", ["Black & White", "Full Color"])
            calc_paper = st.selectbox("Paper Selection", ["Standard", "Glossy"])
            
            p_type_logic = "Glossy" if calc_paper == "Glossy" else "Standard"
            est_cost = calculate_price(calc_pages, calc_color, p_type_logic)
            
            st.markdown(f"### Estimated: ₹{est_cost:.2f}")

    st.divider()
    
    # Centered CTA
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        st.info("Ready to print? Upload your files below.")
        if st.button("UPLOAD DOCUMENTS & ORDER NOW", use_container_width=True):
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
            phone = st.text_input("Phone Number")
        with col2:
            email = st.text_input("Email Address")

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
        if pwd == "admin123": 
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
        
        p = str(row['phone']).strip()
        
        # 1. Remove ANY non-digit characters (including + for a moment to normalize)
        import re
        p_digits = re.sub(r'\D', '', p)
        
        # 2. Check logic for India (+91)
        # If it's a 10 digit number (e.g. 9998887777), treat as local IN number.
        if len(p_digits) == 10:
            final_phone = "+91" + p_digits
        # If it's 12 digits and starts with 91 (e.g. 919998887777), it has country code but no +
        elif len(p_digits) == 12 and p_digits.startswith("91"):
            final_phone = "+" + p_digits
        # If it's more than 10 digits, assume it might be valid with some other code? 
        # But user insists on ensuring +91 is given.
        else:
            # Fallback: Just assume it needs + unless it already has it (which we stripped)
            # Actually, let's just force + prefix if safe
            final_phone = "+" + p_digits if len(p_digits) > 10 else "+91" + p_digits

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
    st.title("Track My Orders 📦")
    st.markdown("View your order history and status.")
    
    # 1. Try to get phone from Cookie
    cookie_phone = cookie_manager.get(cookie="user_phone")
    
    # 2. Input Field (Prefilled if cookie exists)
    phone_input = st.text_input("Enter your Phone Number to track", value=cookie_phone if cookie_phone else "")
    
    if st.button("Track Orders") or phone_input:
        if phone_input:
            # Save to cookie for future
            cookie_manager.set("user_phone", phone_input, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
            
            orders = get_orders_by_phone(phone_input)
            
            if not orders.empty:
                st.success(f"Found {len(orders)} orders for {phone_input}")
                
                for index, row in orders.iterrows():
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([1, 2, 1, 1])
                        with c1:
                            st.write(f"**Order #{row['id']}**")
                            st.caption(row['date'])
                        with c2:
                            st.write(f"**Details:** {row['details']}")
                        with c3:
                            status_color = "orange" if row['status'] == 'Pending' else "green" if row['status'] == 'Completed' else "blue"
                            st.markdown(f"Status: <span style='color:{status_color}; font-weight:bold'>{row['status']}</span>", unsafe_allow_html=True)
                            
                            # Show Payment QR if Waiting for Payment
                            if row['status'] == "Waiting for Payment" and row.get('payment_status', 'Unpaid') == 'Unpaid':
                                with st.expander("💸 Pay Now (QR Code)", expanded=True):
                                    st.image("assets/qr_code.png", width=200)
                                    st.write(f"**Amount: ₹{row['amount']:.2f}**")
                                    st.info("After paying, please wait for 'Paid' status update.")

                        with c4:
                            pay_color = "green" if row.get('payment_status', 'Unpaid') == 'Paid' else "red"
                            st.markdown(f"Pay: <span style='color:{pay_color}; font-weight:bold'>{row.get('payment_status', 'Unpaid')}</span>", unsafe_allow_html=True)
                            st.write(f"**₹{row['amount']:.2f}**")
            else:
                st.warning("No orders found for this number.")
        else:
            st.error("Please enter a phone number.")


# --- MAIN CONTROLLER ---

def main():
    # Sidebar Navigation
    with st.sidebar:
        st.title("Navigation")
        if st.button("🏠 Home"): navigate_to('home')
        if st.button("📦 Track Orders"): navigate_to('track')
        if st.button("🔒 Admin Panel"): navigate_to('admin')

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
