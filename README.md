# Professional Print Services App

A Streamlit web application for a print shop business. Allows customers to upload documents, calculate prices automatically, and send orders via email.

## Features

- **Home Page**: Pricing card, Service details, payment QR code.
- **Order Portal**: Upload PDF/DOCX/Images.
- **Smart Calculation**: Automatically detects page counts in PDFs to estimate price.
- **Manual Override**: User can manually set page count for accurate pricing.
- **Email Integration**: Sends order details and attachments to the shop owner using SMTP.
- **Responsive UI**: Professional, branded design.

## Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/justinsaju21/print_service.git
   cd print_service
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Email**:
   Create a `.streamlit/secrets.toml` file:
   ```toml
   smtp_server = "smtp.gmail.com"
   smtp_port = 587
   sender_email = "your_email@gmail.com"
   sender_password = "your_app_password"
   ```

4. **Run the App**:
   ```bash
   streamlit run app.py
   ```

## Tech Stack
- Python
- Streamlit
- smtplib (Email)
- PyPDF2 (Page Counting)

