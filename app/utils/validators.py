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


def validate_student_id(student_id: Optional[str]) -> bool:
    """Validate student ID format (alphanumeric, max 50 chars)."""
    if not student_id:
        return False
    # Student ID should be alphanumeric with hyphens/underscores, max 50 chars
    pattern = r"^[a-zA-Z0-9_-]{1,50}$"
    return bool(re.match(pattern, student_id))


def validate_document_type(document_type: Optional[str]) -> bool:
    """Validate document type against allowed values."""
    if not document_type:
        return False
    allowed_types = {
        "academic_transcript",
        "degree_certificate",
        "passport",
        "visa",
        "bank_statement",
        "financial_document",
        "english_test_score",
        "standardized_test_score",
        "recommendation_letter",
        "sop",
        "cv_resume",
        "other",
    }
    return document_type.lower() in allowed_types


def validate_file_name(file_name: Optional[str]) -> bool:
    """Validate file name to prevent path traversal and ensure safe names."""
    if not file_name:
        return False
    # File name should not contain path traversal patterns
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        return False
    # Should be alphanumeric with dots, hyphens, underscores, max 255 chars
    pattern = r"^[a-zA-Z0-9._-]{1,255}$"
    if not re.match(pattern, file_name):
        return False
    # Must have a valid file extension
    allowed_extensions = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt"}
    extension = "." + file_name.lower().split(".")[-1] if "." in file_name else ""
    return extension in allowed_extensions
