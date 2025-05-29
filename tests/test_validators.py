# backend/tests/test_validators.py
# Unit tests for validator functions

import pytest
from app.utils.validators import validate_email, validate_phone, validate_score, validate_pincode, validate_cibil_score, validate_pan, validate_aadhaar

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