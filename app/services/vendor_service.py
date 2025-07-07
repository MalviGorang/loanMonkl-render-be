import logging
from typing import Dict, List, Tuple, Optional
import json

logger = logging.getLogger(__name__)


def parse_percentage(value: str) -> float:
    """Convert percentage string to float value."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip("%")) / 100
        except ValueError:
            return 0.75  # Default to 75% if invalid
    return 0.75


def calculate_foir(
    co_applicant_income: float, existing_emi: float, foir_limit: str
) -> float:
    """Calculate FOIR based on income and existing EMI."""
    try:
        if co_applicant_income <= 0:
            return float("inf")
        current_foir = (existing_emi / co_applicant_income) * 100
        return current_foir
    except (TypeError, ZeroDivisionError):
        return float("inf")


def match_vendors(student_profile: Dict, vendors: List[Dict]) -> Tuple[List[Dict], str]:
    """Match student profile with vendor criteria."""
    try:
        logger.info(
            f"Starting vendor matching for student {student_profile.get('student_id')}"
        )

        # Extract university names
        universities = student_profile.get("education_details", {}).get(
            "university_name", []
        )
        if not universities:
            return [], "No university specified in profile"

        # Find vendors supporting the universities
        university_vendors = []
        for university in universities:
            supported_vendors = [
                v["vendorName"] for v in vendors if v.get("active", True)
            ]
            logger.info(
                f"Found vendors for university {university}: {supported_vendors}"
            )
            university_vendors.extend(supported_vendors)

        if not university_vendors:
            return [], "No vendors found supporting the specified universities"

        # Filter to unique vendors
        university_vendors = list(set(university_vendors))
        logger.info(
            f"Filtered to {len(university_vendors)} university-specific vendors"
        )

        # Match vendor criteria
        valid_vendors = []
        for vendor in vendors:
            if (
                not vendor.get("active", True)
                or vendor["vendorName"] not in university_vendors
            ):
                continue

            criteria = vendor.get("criteria", {})

            # Basic eligibility checks
            if not meets_basic_criteria(student_profile, criteria):
                continue

            # FOIR calculation
            co_applicant_details = student_profile.get("co_applicant_details", {})
            co_applicant_income = co_applicant_details.get(
                "co_applicant_income_amount", {}
            ).get("amount", 0)
            existing_emi = co_applicant_details.get(
                "co_applicant_existing_loan_emi_amount", {}
            ).get("amount", 0)

            foir_limit = criteria.get("Foir", criteria.get("foir", "75%"))
            current_foir = calculate_foir(co_applicant_income, existing_emi, foir_limit)

            if current_foir > parse_percentage(foir_limit) * 100:
                continue

            valid_vendors.append(vendor)

        if not valid_vendors:
            return [], "No vendors matched all criteria"

        # Format response
        matches = [format_vendor_match(v, student_profile) for v in valid_vendors]
        return matches, "Successfully matched vendors"

    except Exception as e:
        logger.error(f"Error matching vendors: {str(e)}")
        return [], f"Failed to match vendors: {str(e)}"


def meets_basic_criteria(profile: Dict, criteria: Dict) -> bool:
    """Check if profile meets basic vendor criteria."""
    education = profile.get("education_details", {})

    # Check academic scores
    min_score = criteria.get("min_academic_score_percentage", 0)
    marks_10th = education.get("marks_10th", {}).get("value", 0)
    marks_12th = education.get("marks_12th", {}).get("value", 0)
    if marks_10th < min_score or marks_12th < min_score:
        return False

    # Check backlogs
    max_backlogs = criteria.get("max_educational_backlogs", float("inf"))
    if education.get("educational_backlogs", 0) > max_backlogs:
        return False

    # Check test scores
    english_test = education.get("english_test", {})
    if english_test:
        test_type = english_test.get("type")
        score = english_test.get("score", 0)
        min_score_key = f"min_{test_type.lower()}_score"
        if criteria.get(min_score_key) and score < criteria[min_score_key]:
            return False

    return True


def format_vendor_match(vendor: Dict, profile: Dict) -> Dict:
    """Format vendor match response."""
    criteria = vendor.get("criteria", {})
    return {
        "vendor_name": vendor["vendorName"],
        "vendor_type": vendor.get("vendorType", "Unknown"),
        "max_loan_amount": criteria.get(
            "max_secured_loan_inr"
            if profile.get("loan_details", {}).get("collateral_available") == "Yes"
            else "max_unsecured_loan_inr"
        ),
        "interest_rate": criteria.get(
            "interest_rate_secured"
            if profile.get("loan_details", {}).get("collateral_available") == "Yes"
            else "interest_rate_unsecured"
        ),
        "processing_fee": criteria.get("processing_fee", "1%"),
        "loan_tenor_years": criteria.get("loan_tenor_years"),
        "moratorium_period": criteria.get("moratorium_period"),
        "repayment_options": criteria.get("repayment_options", []),
        "margin_money_percentage": criteria.get("margin_money_percentage", 0),
    }
