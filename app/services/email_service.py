# backend/app/services/email_service.py
# SMTP email service for sending verification emails and OTPs

import smtplib
import ssl
from email.message import EmailMessage
import os
import logging
import random
import string

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_SENDER = os.getenv("EMAIL_SENDER")


def send_verification_email(to_email: str, subject: str, body: str) -> bool:
    """Send a verification email via SMTP."""
    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_SENDER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info(f"Verification email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send verification email to {to_email}: {e}")
        return False


def generate_otp() -> str:
    """Generate a 6-digit OTP."""
    return ''.join(random.choices(string.digits, k=6))


def send_otp_email(to_email: str, otp: str, purpose: str = "verification") -> bool:
    """Send OTP via email."""
    try:
        subject = f"Your OTP for {purpose}"
        body = f"""
Hello,

Your OTP (One-Time Password) for {purpose} is: {otp}

This OTP is valid for 10 minutes only. Please do not share this code with anyone.

If you didn't request this OTP, please ignore this email.

Best regards,
LoanMonk Team
        """
        
        msg = EmailMessage()
        msg["From"] = EMAIL_SENDER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body.strip())

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info(f"OTP email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email to {to_email}: {e}")
        return False 