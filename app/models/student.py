# backend/app/models/student.py
# Pydantic model for student profile

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List, Union
from datetime import datetime


class AmountCurrency(BaseModel):
    """Model for amount with currency."""

    amount: Optional[float] = None
    currency: Optional[str] = None


class EducationDetails(BaseModel):
    """Model for education details."""

    marks_10th: Optional[Dict] = None
    marks_12th: Optional[Dict] = None
    highest_education_level: Optional[str] = None
    academic_score: Optional[Dict] = None
    educational_backlogs: Optional[Union[int, str]] = None  # Allow both int and str
    education_gap: Optional[str] = None
    education_gap_duration: Optional[Union[int, str]] = None  # Allow both int and str
    current_profession: Optional[str] = None
    university_admission_status: Optional[str] = None
    study_destination_country: Optional[Union[str, List[str]]] = (
        None  # Allow both str and list
    )
    university_name: Optional[Union[str, List[str]]] = None  # Allow both str and list
    intended_degree: Optional[str] = None
    course_type: Optional[str] = None  # STEM, Non-STEM, Management, Other
    specific_course_name: Optional[str] = None
    target_intake: Optional[str] = None
    course_duration: Optional[Dict] = None
    english_test: Optional[Dict] = None
    standardized_test: Optional[Dict] = None
    loan_amount_requested: Optional[AmountCurrency] = None
    admission_status: Optional[str] = Field(
        None, description="Student's admission status"
    )


class LoanDetails(BaseModel):
    """Model for loan details."""

    loan_amount_requested: Optional[AmountCurrency] = None
    collateral_available: Optional[str] = Field(None)
    collateral_type: Optional[str] = Field(None)
    collateral_value_amount: Optional[Dict[str, Any]] = Field(None)
    collateral_location_pincode: Optional[str] = Field(None)
    collateral_location_city: Optional[str] = Field(None)
    collateral_location_state: Optional[str] = Field(None)
    collateral_existing_loan: Optional[str] = None
    collateral_existing_loan_amount: Optional[AmountCurrency] = None
    collateral_existing_loan_emi_amount: Optional[AmountCurrency] = None
    co_applicant_available: Optional[str] = None
    cibil_score: Optional[str] = None
    pan: Optional[str] = None
    aadhaar: Optional[str] = None
    co_applicant_pan: Optional[str] = None
    co_applicant_aadhaar: Optional[str] = None

    @validator(
        "collateral_location_pincode",
        "collateral_type",
        "collateral_value_amount",
        "collateral_location_city",
        "collateral_location_state",
    )
    def clear_if_no_collateral(cls, v, values):
        if values.get("collateral_available") == "No":
            return None
        return v


class CoApplicantDetails(BaseModel):
    """Model for co-applicant details."""

    co_applicant_relation: Optional[str] = None
    co_applicant_occupation: Optional[str] = None
    co_applicant_income_amount: Optional[AmountCurrency] = None
    co_applicant_existing_loan: Optional[str] = None
    co_applicant_existing_loan_amount: Optional[AmountCurrency] = None
    co_applicant_existing_loan_emi_amount: Optional[AmountCurrency] = None
    co_applicant_emi_default: Optional[str] = None
    co_applicant_house_ownership: Optional[str] = Field(
        None, description="Whether co-applicant owns a house (Yes/No)"
    )
    co_applicant_maintains_average_balance: Optional[str] = Field(
        None, description="Whether co-applicant maintains average balance (Yes/No)"
    )


class Student(BaseModel):
    """Model for student profile."""

    student_id: Optional[str] = None

    name: Optional[str] = None  # Fixed: added default value
    mobile_number: Optional[str] = None  # Fixed: added default value
    email: Optional[str] = None  # Fixed: added default value
    date_of_birth: Optional[str] = None
    current_location_pincode: Optional[str] = None

    name: Optional[str]
    mobile_number: Optional[str]
    email: Optional[str]
    date_of_birth: Optional[str]
    current_location_pincode: Optional[str]

    current_location_city: Optional[str] = None
    current_location_state: Optional[str] = None
    current_profession: Optional[str] = None
    education_details: Optional[EducationDetails] = None
    loan_details: Optional[LoanDetails] = None
    co_applicant_details: Optional[CoApplicantDetails] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
