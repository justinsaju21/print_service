import streamlit as st
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import PyPDF2

# --- CONFIGURATION & STYLING ---
st.set_page_config(
    page_title="Professional Print Services",
    page_icon="🖨️",
    layout="wide"
)

# Initialize Session State
if 'page' not in st.session_state:
    st.session_state['page'] = 'home'

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
    
    /* Price Card Styling */
    .price-card {
        background: white;
        padding: 25px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        border-top: 5px solid #1565c0;
        height: 100%;
        transition: transform 0.2s;
        color: #333333; /* Explicitly force dark text */
    }
    .price-card:hover {
        transform: translateY(-5px);
    }
    .price-card h3 {
        margin-top: 0;
        border-bottom: 1px solid #eee;
        padding-bottom: 10px;
        color: #1565c0; /* Brand color for header */
    }
    .price-card ul {
        list-style-type: none;
        padding: 0;
        color: #444; /* Dark gray for list items */
    }
    .price-card li {
        padding: 8px 0;
        font-size: 1.1rem;
        border-bottom: 1px solid #f0f0f0;
    }
    
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
    
    # Updated to 1:1 ratio for symmetry
    col1, col2 = st.columns(2, gap="large")
    
    with col1:
        st.markdown("""
        <div class="price-card">
            <h3>Pricing Info</h3>
            <ul>
                <li><strong>Black & White:</strong> ₹2 per page</li>
                <li><strong>Full Color:</strong> ₹10 per page</li>
                <li><strong>Glossy Paper:</strong> ₹20 per page</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        
        st.write("") # Spacer
        
        st.subheader("Quick Cost Calculator")
        with st.container(border=True):
            calc_pages = st.number_input("Number of Pages", min_value=1, value=10)
            calc_color = st.selectbox("Color Mode", ["Black & White", "Full Color"])
            calc_paper = st.selectbox("Paper Selection", ["Standard", "Glossy"])
            
            p_type_logic = "Glossy" if calc_paper == "Glossy" else "Standard"
            est_cost = calculate_price(calc_pages, calc_color, p_type_logic)
            
            st.markdown(f"### Estimated: ₹{est_cost:.2f}")

    with col2:
        # Centering the QR code visually in the column
        st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
        st.image("assets/qr_code.png", caption="Scan to Pay via GPay", width=300)
        st.info("Note: Please wait for order confirmation on WhatsApp before making payment.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()
    
    # Centered 'cta' button
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
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
            
            # Manual Override Option
            if st.checkbox("Incorrect page count? Click to manually set pages."):
                detected_pages = st.number_input("Enter actual total number of pages", min_value=1, value=detected_pages)
                st.caption("Use this for Word documents or files where auto-detection might be inaccurate.")


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
    submit_order = st.button("Confirm & Send Order", type="primary", use_container_width=True)
    
    if submit_order:
        missing = []
        if not name: missing.append("Name")
        if not phone: missing.append("Phone")
        if not uploaded_files: missing.append("Files")
        
        if missing:
            st.error(f"Please provide: {', '.join(missing)}")
        else:
            with st.spinner("Processing Order..."):
                order_data = {
                    "color": color_mode,
                    "paper": paper_type,
                    "sides": sides,
                    "pages": detected_pages
                }
                
                success, msg = send_email(name, email, phone, order_data, uploaded_files, comments, estimated_total, file_info)
                
                if success:
                    st.success("Order Sent Successfully!")
                    st.balloons()
                    
                    st.markdown("""
                    <div style="background-color: #e3f2fd; padding: 20px; border-radius: 10px; text-align: center; border-left: 5px solid #2196f3;">
                        <h3 style="color: #0d47a1; margin-top: 0;">Order Received! ✅</h3>
                        <p style="font-size: 1.1em;">We have received your order details.</p>
                        <p style="font-size: 1.1em; font-weight: bold; color: #d32f2f;">
                            ⚠️ PLEASE WAIT for a confirmation message on WhatsApp before making the payment.
                        </p>
                        <p>Once confirmed, you can scan the QR code below.</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    with st.expander("View Payment QR Code"):
                         st.image("assets/qr_code.png", width=250, caption="Scan to Pay (Wait for confirmation first)")
                         st.info(f"Amount to Pay: ₹{estimated_total:.2f}")

                else:
                    if "SMTP" in msg or "missing" in msg: 
                         st.warning("Order Processed (Demo Mode)")
                         st.write(f"Email would be sent to shop owner. Setup secrets.toml to enable real sending.")
                         st.error(f"System Message: {msg}")
                    else:
                        st.error(f"Failed to send: {msg}")

# --- MAIN CONTROLLER ---

def main():
    if st.session_state['page'] == 'home':
        home_view()
    else:
        order_view()

if __name__ == "__main__":
    main()
