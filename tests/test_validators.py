# backend/tests/test_validators.py
# Unit tests for validator functions

import pytest
from app.utils.validators import (
    validate_email,
    validate_phone,
    validate_score,
    validate_pincode,
    validate_cibil_score,
    validate_pan,
    validate_aadhaar,
    validate_student_id,
    validate_document_type,
    validate_file_name,
)


def test_validate_email():
    """Test email validation."""
    assert validate_email(None) == True
    assert validate_email("test@example.com") == True
    assert validate_email("invalid") == False


def test_validate_phone():
    """Test phone number validation."""
    assert validate_phone(None) == True
    assert validate_phone("+919876543210") == True
    assert validate_phone("123") == False


def test_validate_score():
    """Test score validation."""
    assert validate_score(None, "Percentage", 0, 100) == True
    assert validate_score(85, "Percentage", 0, 100) == True
    assert validate_score(7.5, "CGPA", 0, 10) == True
    assert validate_score(150, "Percentage", 0, 100) == False


def test_validate_pincode():
    """Test pincode validation."""
    assert validate_pincode(None) == True
    assert validate_pincode("560066") == True
    assert validate_pincode("123") == False


def test_validate_cibil_score():
    """Test CIBIL score validation."""
    assert validate_cibil_score(None) == True
    assert validate_cibil_score("720") == True
    assert validate_cibil_score("200") == False
    assert validate_cibil_score("abc") == False


def test_validate_pan():
    """Test PAN number validation."""
    assert validate_pan(None) == True
    assert validate_pan("ABCDE1234F") == True
    assert validate_pan("12345") == False


def test_validate_aadhaar():
    """Test Aadhaar number validation."""
    assert validate_aadhaar(None) == True
    assert validate_aadhaar("123456789012") == True
    assert validate_aadhaar("12345") == False


def test_validate_student_id():
    """Test student ID validation."""
    assert validate_student_id(None) == False
    assert validate_student_id("") == False
    assert validate_student_id("STU123") == True
    assert validate_student_id("stu_123-abc") == True
    assert validate_student_id("123") == True
    assert validate_student_id("a" * 51) == False  # Too long
    assert validate_student_id("stu@123") == False  # Invalid character


def test_validate_document_type():
    """Test document type validation."""
    assert validate_document_type(None) == False
    assert validate_document_type("") == False
    assert validate_document_type("academic_transcript") == True
    assert validate_document_type("passport") == True
    assert validate_document_type("invalid_type") == False
    assert validate_document_type("PASSPORT") == True  # Case insensitive
    assert validate_document_type("Academic_Transcript") == True  # Case insensitive


def test_validate_file_name():
    """Test file name validation."""
    assert validate_file_name(None) == False
    assert validate_file_name("") == False
    assert validate_file_name("document.pdf") == True
    assert validate_file_name("my_document.docx") == True
    assert validate_file_name("image.jpg") == True
    assert validate_file_name("../../../etc/passwd") == False  # Path traversal
    assert validate_file_name("document/subdir.pdf") == False  # Directory separator
    assert validate_file_name("document.exe") == False  # Invalid extension
    assert validate_file_name("a" * 256) == False  # Too long
