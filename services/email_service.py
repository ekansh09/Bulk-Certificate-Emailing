"""
Email sending service via Gmail SMTP.

Handles SMTP connection management and message construction.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from retrying import retry


def test_connection(email, password):
    """Test SMTP connection with provided credentials. Raises on failure."""
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(email, password)
    server.quit()


def create_connection(email, password):
    """Create and return an authenticated SMTP connection."""
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(email, password)
    return server


def build_message(from_addr, to_addr, subject, body_plain, body_html, pdf_path):
    """Build a MIME email with plain text, HTML body, and PDF attachment."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr
    msg.attach(MIMEText(body_plain, 'plain'))
    msg.attach(MIMEText(body_html, 'html'))

    with open(pdf_path, 'rb') as f:
        part = MIMEApplication(f.read(), _subtype='pdf')
    part.add_header(
        'Content-Disposition', 'attachment',
        filename=os.path.basename(pdf_path),
    )
    msg.attach(part)
    return msg


@retry(stop_max_attempt_number=3, wait_fixed=2000)
def send_message(server, msg):
    """Send an email message with automatic retries."""
    server.send_message(msg)
