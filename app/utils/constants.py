# backend/app/utils/constants.py
# Defines constants for question details and currency options

from enum import Enum

# Enum for currency codes
class CurrencyCode(str, Enum):
    """Enum for supported currency codes."""
    INR = "INR"
    USD = "USD"

# List of currency options
CURRENCY_OPTIONS = [c.value for c in CurrencyCode]

# Question details with conditions for modals
QUESTION_DETAILS = {
    "name": {"text": "What's your full name?", "type": "text"},
    "mobile_number": {"text": "What's your mobile number? (With country code, e.g., +919876543210)", "type": "text"},
    "email": {"text": "What's your email address?", "type": "text"},
    "date_of_birth": {"text": "What's your date of birth? (DD/MM/YYYY)", "type": "date"},
    "current_location_pincode": {"text": "What's your 6-digit home pincode?", "type": "text"},
    "marks_10th": {
        "text": "What was your 10th standard score? (Enter format and score, e.g., 85% or 7.5 CGPA)",
        "type": "score_format_combo",
        "options": [
            {"format": "Percentage", "range": {"min": 0, "max": 100}},
            {"format": "CGPA", "range": {"min": 0, "max": 10}}
        ]
    },
    "marks_12th": {
        "text": "What was your 12th standard score? (Enter format and score, e.g., 90% or 8.0 CGPA)",
        "type": "score_format_combo",
        "options": [
            {"format": "Percentage", "range": {"min": 0, "max": 100}},
            {"format": "CGPA", "range": {"min": 0, "max": 10}}
        ]
    },
    "highest_education_level": {
        "text": "What's your highest education level? (Choose one)",
        "type": "choice",
        "options": ["High School", "UG_Diploma", "Bachelors", "Masters", "PG_Diploma", "PG", "Other"]
    },
    "academic_score": {
        "text": "What's the score of your highest degree? (Enter format and score)",
        "type": "score_format_combo",
        "options": [
            {"format": "Percentage", "range": {"min": 0, "max": 100}},
            {"format": "CGPA", "range": {"min": 0, "max": 10}}
        ],
        "condition": "highest_education_level != 'High School'",
        "explanation": "This question is skipped if the highest education level is High School."
    },
    "educational_backlogs": {
        "text": "Do you have any backlogs?",
        "type": "choice",
        "options": [str(i) for i in range(21)]
    },
    "education_gap": {"text": "Did you have a gap in your education?", "type": "boolean", "options": ["Yes", "No"]},
    "education_gap_duration": {
        "text": "How long was your education gap? (in months)",
        "type": "choice",
        "options": [str(i) for i in range(0, 31)],
        "condition": "education_gap == 'Yes'",
        "explanation": "This question is only asked if the student indicates an education gap."
    },
    "current_profession": {
        "text": "What is your current profession?",
        "type": "choice",
        "options": ["Student", "Employed", "Unemployed", "Self-Employed", "Other"]
    },
    "yearly_income": {
        "text": "What's your yearly income? (Choose a currency)",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS,
        "condition": "current_profession in ['Employed', 'Self-Employed']",
        "explanation": "This question is relevant for employed or self-employed individuals."
    },
    "collateral_type": {
        "text": "Do you have any collateral like FD or property?",
        "type": "choice",
        "options": ["FD", "Self-Property", "No"],
        "condition": "current_profession in ['Unemployed', 'Other']",
        "explanation": "This question is relevant for unemployed or other professions."
    },
    "collateral_existing_loan": {
        "text": "Is there an existing loan on this collateral?",
        "type": "boolean",
        "options": ["Yes", "No"],
        "condition": "collateral_type in ['FD', 'Self-Property']",
        "explanation": "This question is asked if collateral is FD or Self-Property."
    },
    "collateral_loan_amount": {
        "text": "What's the existing loan amount on your collateral?",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS,
        "condition": "collateral_existing_loan == 'Yes'",
        "explanation": "This question is asked if there is an existing loan on collateral."
    },
    "university_admission_status": {
        "text": "Have you received your admission letter?",
        "type": "choice",
        "options": ["Admission letter received", "Conditional letter received", "Admission letter not received", "Admission rejected", "Not applied"]
    },
    "study_destination_country": {
        "text": "Which country will you study in? (Select up to 3 if not applied)",
        "type": "multi_choice",
        "condition": "university_admission_status not in ['Admission letter not received', 'Not applied']",
        "explanation": "This question is asked if the student has received an admission letter."
    },
    "university_name": {
        "text": "What's the name of your university? (Select up to 5 if not applied)",
        "type": "multi_choice",
        "condition": "university_admission_status not in ['Admission letter not received', 'Not applied']",
        "explanation": "This question is asked if the student has received an admission letter."
    },
    "intended_degree": {
        "text": "Which degree will you pursue? (Choose one)",
        "type": "choice",
        "options": ["Bachelors", "Masters", "PhD", "Diploma", "Certificate", "Other"]
    },
    "specific_course_name": {
        "text": "What course will you study? (Choose one)",
        "type": "choice"
    },
    "target_intake": {
        "text": "Which intake are you aiming for?",
        "type": "choice",
        "options": ["Spring", "Fall", "Summer", "Winter"]
    },
    "course_duration": {
        "text": "How long is your course? (Years and months)",
        "type": "course_duration",
        "options": [["0", "1", "2", "3", "4", "5", "6"], ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]]
    },
    "loan_amount_requested": {
        "text": "How much loan do you need? (Choose a currency)",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS
    },
    "english_test": {
        "text": "Which English test did you take? (Choose one and enter score)",
        "type": "test_score_combo",
        "options": [
            {"type": "IELTS", "range": {"min": 0.0, "max": 9.0}},
            {"type": "TOEFL", "range": {"min": 0, "max": 120}},
            {"type": "PTE", "range": {"min": 10, "max": 90}},
            {"type": "Duolingo", "range": {"min": 10, "max": 160}},
            {"type": "None"}
        ]
    },
    "standardized_test": {
        "text": "Did you take a standardized test like GRE or GMAT? (Choose one and enter score)",
        "type": "test_score_combo",
        "options": [
            {"type": "GRE", "range": {"min": 260, "max": 340}},
            {"type": "GMAT", "range": {"min": 200, "max": 800}},
            {"type": "None"}
        ]
    },
    "collateral_available": {
        "text": "Do you have collateral for a secured loan? (e.g., property, FD)",
        "type": "choice",
        "options": ["Yes", "No"]
    },
    "collateral_type": {
        "text": "What type of collateral do you have?",
        "type": "choice",
        "options": ["Residential", "Commercial", "Land", "Farm Land", "FD"],
        "condition": "collateral_available == 'Yes'",
        "explanation": "This question is asked if the student has collateral available."
    },
    "collateral_value_amount": {
        "text": "What's the value of your collateral? (Choose a currency)",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS,
        "condition": "collateral_available == 'Yes'",
        "explanation": "This question is asked if the student has collateral available."
    },
    "collateral_location_pincode": {
        "text": "What's the 6-digit pincode of your property?",
        "type": "text",
        "condition": "collateral_type != 'FD'",
        "explanation": "This question is skipped if the collateral type is FD."
    },
    "collateral_existing_loan": {
        "text": "Is there an existing loan on this collateral?",
        "type": "boolean",
        "options": ["Yes", "No"],
        "condition": "collateral_available == 'Yes'",
        "explanation": "This question is asked if the student has collateral available."
    },
    "collateral_existing_loan_amount": {
        "text": "What's the remaining loan amount on your collateral?",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS,
        "condition": "collateral_existing_loan == 'Yes'",
        "explanation": "This question is asked if there is an existing loan on collateral."
    },
    "collateral_existing_loan_emi_amount": {
        "text": "What's the monthly EMI for this existing loan?",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS,
        "condition": "collateral_existing_loan == 'Yes'",
        "explanation": "This question is asked if there is an existing loan on collateral."
    },
    "co_applicant_available": {
        "text": "Do you have a co-applicant for your loan?",
        "type": "boolean",
        "options": ["Yes", "No"]
    },
    "co_applicant_relation": {
        "text": "Who is your co-applicant? (Choose one)",
        "type": "choice",
        "options": ["Father", "Mother", "Brother", "Sister", "Other"],
        "condition": "co_applicant_available == 'Yes'",
        "explanation": "This question is asked if the student has a co-applicant."
    },
    "co_applicant_occupation": {
        "text": "What's your co-applicant's occupation?",
        "type": "choice",
        "options": ["Salaried", "Self-Employed", "Farmer", "Unemployed", "Other"],
        "condition": "co_applicant_available == 'Yes'",
        "explanation": "This question is asked if the student has a co-applicant."
    },
    "co_applicant_income_amount": {
        "text": "What's your co-applicant's yearly income? (Choose a currency)",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS,
        "condition": "co_applicant_available == 'Yes'",
        "explanation": "This question is asked if the student has a co-applicant."
    },
    "co_applicant_existing_loan": {
        "text": "Does your co-applicant have any existing loans?",
        "type": "boolean",
        "options": ["Yes", "No"],
        "condition": "co_applicant_available == 'Yes'",
        "explanation": "This question is asked if the student has a co-applicant."
    },
    "co_applicant_existing_loan_amount": {
        "text": "What's the remaining loan amount for your co-applicant?",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS,
        "condition": "co_applicant_existing_loan == 'Yes'",
        "explanation": "This question is asked if the co-applicant has existing loans."
    },
    "co_applicant_existing_loan_emi_amount": {
        "text": "What's the monthly EMI for your co-applicant's loans?",
        "type": "amount_currency",
        "options": CURRENCY_OPTIONS,
        "condition": "co_applicant_existing_loan == 'Yes'",
        "explanation": "This question is asked if the co-applicant has existing loans."
    },
    "co_applicant_emi_default": {
        "text": "Has your co-applicant defaulted on any EMI in the last 10 years?",
        "type": "boolean",
        "options": ["Yes", "No"],
        "condition": "co_applicant_existing_loan == 'Yes'",
        "explanation": "This question is asked if the co-applicant has existing loans."
    },
    "cibil_score": {
        "text": "What's your CIBIL score?",
        "type": "text"
    },
    "pan": {
        "text": "What's your PAN number? (Optional, but can speed up your loan)",
        "type": "text"
    },
    "aadhaar": {
        "text": "What's your Aadhaar number? (Optional, but can speed up your loan)",
        "type": "text"
    },
    "co_applicant_pan": {
        "text": "What's your co-applicant's PAN number? (Optional)",
        "type": "text",
        "condition": "co_applicant_available == 'Yes'",
        "explanation": "This question is asked if the student has a co-applicant."
    },
    "co_applicant_aadhaar": {
        "text": "What's your co-applicant's Aadhaar number? (Optional)",
        "type": "text",
        "condition": "co_applicant_available == 'Yes'",
        "explanation": "This question is asked if the student has a co-applicant."
    }
}