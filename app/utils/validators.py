# backend/app/utils/validators.py
# Validation functions for input data

import re
from typing import Optional


def validate_email(email: Optional[str]) -> bool:
    """Validate email format if provided."""
    if not email:
        return True
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_phone(phone: Optional[str]) -> bool:
    """Validate phone number format if provided."""
    if not phone:
        return True
    # Phone should be 7-15 digits, optionally starting with +
    # First digit (after +) should be 1-9, followed by 6-14 more digits
    pattern = r"^\+?[1-9]\d{6,14}$"
    return bool(re.match(pattern, phone))


def validate_score(
    value: Optional[float], format_type: str, min_val: float, max_val: float
) -> bool:
    """Validate score within specified range if provided."""
    if value is None:
        return True
    return min_val <= value <= max_val


def validate_pincode(pincode: Optional[str]) -> bool:
    """Validate 6-digit pincode if provided."""
    if not pincode:
        return True
    return bool(re.match(r"^\d{6}$", pincode))


def validate_cibil_score(score: Optional[str]) -> bool:
    """Validate CIBIL score if provided."""
    if not score:
        return True
    try:
        value = int(score)
        return 300 <= value <= 900
    except ValueError:
        return False


def validate_pan(pan: Optional[str]) -> bool:
    """Validate PAN number format if provided."""
    if not pan:
        return True
    pattern = r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$"
    return bool(re.match(pattern, pan))


def validate_aadhaar(aadhaar: Optional[str]) -> bool:
    """Validate Aadhaar number format if provided."""
    if not aadhaar:
        return True
    pattern = r"^\d{12}$"
    return bool(re.match(pattern, aadhaar))
