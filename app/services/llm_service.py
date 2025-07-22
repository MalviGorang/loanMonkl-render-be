import os
import json
import re
import logging
import requests
from typing import Optional, Tuple, List, Dict
from datetime import datetime
import time
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
from collections import OrderedDict
from functools import lru_cache
from openai import OpenAI

# Import VENDORS from utils/vendors_list.py
from ..utils.vendors_list import VENDORS  # Adjusted import path

# Load environment variables
load_dotenv()

# Configure logging with UTF-8 support
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Currency conversion API configuration
EXCHANGE_RATE_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
CURRENCYLAYER_API_KEY = os.getenv("CURRENCYLAYER_API_KEY")
EXCHANGE_RATE_URL = "https://api.exchangerate-api.com/v4/latest/USD"
CURRENCYLAYER_URL = "http://api.currencylayer.com/live"


@lru_cache(maxsize=1)
def get_usd_to_inr_rate() -> float:
    """Fetch real-time USD to INR exchange rate with caching."""
    try:
        if not EXCHANGE_RATE_API_KEY:
            logger.warning("ExchangeRate-API key missing, using default rate 83.0")
            return 83.0
        response = requests.get(
            EXCHANGE_RATE_URL, params={"api_key": EXCHANGE_RATE_API_KEY}, timeout=5
        )
        response.raise_for_status()
        data = response.json()
        rate = data.get("rates", {}).get("INR")
        if not rate:
            logger.error("INR rate not found in ExchangeRate-API response")
            return try_currencylayer()
        logger.info(f"Fetched USD to INR rate from ExchangeRate-API: {rate}")
        return float(rate)
    except Exception as e:
        logger.warning(f"ExchangeRate-API failed: {str(e)}, trying CurrencyLayer")
        return try_currencylayer()


def try_currencylayer() -> float:
    """Fallback to CurrencyLayer for USD to INR rate."""
    try:
        if not CURRENCYLAYER_API_KEY:
            logger.warning("CurrencyLayer API key missing, using default rate 83.0")
            return 83.0
        response = requests.get(
            CURRENCYLAYER_URL,
            params={"access_key": CURRENCYLAYER_API_KEY, "currencies": "INR"},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()
        rate = data.get("quotes", {}).get("USDINR")
        if not rate:
            logger.error("INR rate not found in CurrencyLayer response")
            return 83.0
        logger.info(f"Fetched USD to INR rate from CurrencyLayer: {rate}")
        return float(rate)
    except Exception as e:
        logger.error(f"CurrencyLayer failed: {str(e)}, using default rate 83.0")
        return 83.0


# MongoDB configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/FA_bots")
try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command("ping")
    db = mongo_client.get_database("FA_bots")
    universities_collection = db["universities"]
    logger.info("Successfully connected to MongoDB")
except ConnectionFailure as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    universities_collection = None


def format_amount(amount: float) -> str:
    """Format amount with commas and approximate in words if large."""
    if amount is None or amount == 0:
        return "0"
    formatted = "{:,.2f}".format(amount)
    if amount >= 10000000:
        crores = amount / 10000000
        return f"{formatted} (~{crores:.1f} Crore)"
    elif amount >= 100000:
        lakhs = amount / 100000
        return f"{formatted} (~{lakhs:.1f} Lakh)"
    return formatted


def validate_profile(profile: Dict) -> Dict:
    """Validate and normalize student profile fields."""
    validated = profile.copy()
    validated["co_applicant_details"] = validated.get("co_applicant_details", {})
    validated["loan_details"] = validated.get("loan_details", {})
    validated["education_details"] = validated.get("education_details", {})

    # own_house
    co_applicant_house_ownership = validated["co_applicant_details"].get(
        "co_applicant_house_ownership"
    )
    if co_applicant_house_ownership is not None:
        validated["own_house"] = co_applicant_house_ownership in ("Yes", True, "True")
        logger.info(
            f"Set own_house to {validated['own_house']} based on co_applicant_house_ownership"
        )
    elif "own_house" not in validated:
        logger.warning(
            "own_house and co_applicant_house_ownership missing, defaulting to False; may exclude vendors requiring own house"
        )
        validated["own_house"] = False
    else:
        validated["own_house"] = validated["own_house"] in (True, "True", "Yes")

    # co_applicant_bank_balance
    co_applicant_maintains_balance = validated["co_applicant_details"].get(
        "co_applicant_maintains_average_balance"
    )
    if co_applicant_maintains_balance is not None:
        validated["co_applicant_details"]["bank_balance"] = (
            co_applicant_maintains_balance in ("Yes", True, "True")
        )
        logger.info(
            f"Set bank_balance to {validated['co_applicant_details']['bank_balance']} based on co_applicant_maintains_average_balance"
        )
    else:
        validated["co_applicant_details"]["bank_balance"] = validated[
            "co_applicant_details"
        ].get("bank_balance", False) in (True, "True", "Yes")

    # loan_amount_requested
    loan_amt = validated.get("loan_details", {}).get(
        "loan_amount_requested",
        validated.get("education_details", {}).get("loan_amount_requested", {}),
    )
    if (
        not isinstance(loan_amt, dict)
        or not isinstance(loan_amt.get("amount"), (int, float))
        or loan_amt.get("amount", 0) <= 0
    ):
        raise ValueError(
            "Invalid loan_amount_requested: must be a dictionary with positive amount"
        )
    validated["loan_details"]["loan_amount_requested"] = {
        "amount": float(loan_amt.get("amount")),
        "currency": loan_amt.get("currency", "INR").upper(),
    }

    # cibil_score
    cibil = validated["loan_details"].get("cibil_score", "None")
    validated["loan_details"]["cibil_score"] = (
        cibil
        if (cibil == "None" or (isinstance(cibil, str) and cibil.isdigit()))
        else "None"
    )

    # co_applicant_income_amount
    income = validated["co_applicant_details"].get("co_applicant_income_amount", {})
    validated["co_applicant_details"]["co_applicant_income_amount"] = {
        "amount": max(float(income.get("amount", 0)), 0),
        "currency": income.get("currency", "INR").upper(),
    }

    # admission_status
    valid_statuses = ["Admission letter received", "Conditional letter received", ""]
    validated["education_details"]["admission_status"] = (
        validated["education_details"].get("admission_status", "")
        if validated["education_details"].get("admission_status", "") in valid_statuses
        else ""
    )

    # test scores
    english_test = validated["education_details"].get("english_test", {})
    if isinstance(english_test, dict) and "score" in english_test:
        try:
            validated["education_details"]["english_test"]["score"] = float(
                english_test["score"]
            )
        except (ValueError, TypeError):
            validated["education_details"]["english_test"]["score"] = None
    standardized_test = validated["education_details"].get("standardized_test", {})
    if isinstance(standardized_test, dict) and "score" in standardized_test:
        try:
            validated["education_details"]["standardized_test"]["score"] = float(
                standardized_test["score"]
            )
        except (ValueError, TypeError):
            validated["education_details"]["standardized_test"]["score"] = None

    return validated



# FOIR Calculation

def calculate_foir(
    student_profile: Dict,
    vendor: Dict,
    requested_loan_amount: float,
    loan_preference: str,
    interest_rate: Optional[float] = None,
    tenure_years: Optional[float] = None,
    exchange_rate: Optional[float] = None,
    foir_limit: Optional[float] = None,
) -> Tuple[float, float, str]:
    vendor_name = vendor.get("vendorName", "Unknown")

    logger.info("Calculating FOIR for student profile with loan amount: %s INR for vendor %s", format_amount(requested_loan_amount), vendor_name)

    if loan_preference not in ["Secured", "Unsecured"]:
        logger.error("Invalid loan_preference: %s for vendor %s", loan_preference, vendor_name)

    logger.info(
        f"Calculating FOIR for student profile with loan amount: {format_amount(requested_loan_amount)} INR for vendor {vendor_name}"
    )

    if loan_preference not in ["Secured", "Unsecured"]:
        logger.error(
            f"Invalid loan_preference: {loan_preference} for vendor {vendor_name}"
        )

        return 0, requested_loan_amount, f"Invalid loan preference: {loan_preference}"

    education_details = student_profile.get("education_details", {})
    loan_details = student_profile.get("loan_details", {})
    co_applicant_details = student_profile.get("co_applicant_details", {})

    criteria = vendor.get("criteria", {})
    
    yearly_income = co_applicant_details.get("co_applicant_income_amount", {}).get("amount", 0) if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict) else 0
    currency = co_applicant_details.get("co_applicant_income_amount", {}).get("currency", "INR") if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict) else "INR"
    student_income = student_profile.get("education_details", {}).get("current_income_amount", {}).get("amount", 0) if isinstance(student_profile.get("education_details", {}).get("current_income_amount"), dict) else 0
    student_currency = student_profile.get("education_details", {}).get("current_income_amount", {}).get("currency", "INR") if isinstance(student_profile.get("education_details", {}).get("current_income_amount"), dict) else "INR"

    yearly_income = (
        co_applicant_details.get("co_applicant_income_amount", {}).get("amount", 0)
        if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict)
        else 0
    )
    currency = (
        co_applicant_details.get("co_applicant_income_amount", {}).get(
            "currency", "INR"
        )
        if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict)
        else "INR"
    )
    student_income = (
        student_profile.get("education_details", {})
        .get("current_income_amount", {})
        .get("amount", 0)
        if isinstance(
            student_profile.get("education_details", {}).get("current_income_amount"),
            dict,
        )
        else 0
    )
    student_currency = (
        student_profile.get("education_details", {})
        .get("current_income_amount", {})
        .get("currency", "INR")
        if isinstance(
            student_profile.get("education_details", {}).get("current_income_amount"),
            dict,
        )
        else "INR"
    )


    exchange_rate = exchange_rate or get_usd_to_inr_rate()
    if currency != "INR":
        yearly_income *= exchange_rate

        logger.info("Converted co-applicant income to INR: %s for vendor %s", format_amount(yearly_income), vendor_name)
    if student_currency != "INR":
        student_income *= exchange_rate
        logger.info("Converted student income to INR: %s for vendor %s", format_amount(student_income), vendor_name)
    
    total_yearly_income = yearly_income + student_income
    monthly_income = total_yearly_income / 12 if total_yearly_income > 0 else 0

    if not total_yearly_income and criteria.get("requires_co_applicant", False):
        logger.warning("No income provided for vendor %s requiring co-applicant", vendor_name)

        logger.info(
            f"Converted co-applicant income to INR: {format_amount(yearly_income)} for vendor {vendor_name}"
        )
    if student_currency != "INR":
        student_income *= exchange_rate
        logger.info(
            f"Converted student income to INR: {format_amount(student_income)} for vendor {vendor_name}"
        )

    total_yearly_income = yearly_income + student_income
    monthly_income = total_yearly_income / 12 if total_yearly_income > 0 else 0

    # Validate income
    if not total_yearly_income and vendor.get("criteria", {}).get(
        "requires_co_applicant", False
    ):
        logger.warning(
            f"No income provided for vendor {vendor_name} requiring co-applicant"
        )

        
        return 0, requested_loan_amount, "No income provided"

    foir_limit = foir_limit or (0.75 if monthly_income >= 100000 else 0.60)

    logger.info("FOIR limit for %s: %.1f%%", co_applicant_details.get('co_applicant_occupation', 'Salaried'), foir_limit*100)

    existing_emi = co_applicant_details.get("co_applicant_existing_loan_emi_amount", {}).get("amount", 0) if isinstance(co_applicant_details.get("co_applicant_existing_loan_emi_amount"), dict) else 0
    logger.info("Existing EMI: %s INR for vendor %s", format_amount(existing_emi), vendor_name)

    interest_rate_key = "interest_rate_secured" if loan_preference == "Secured" else "interest_rate_unsecured"
    interest_rate = interest_rate or criteria.get(interest_rate_key, 10.0)
    if interest_rate == 10.0 and interest_rate_key not in criteria:
        logger.warning("No %s found for vendor %s, using default 10%%", interest_rate_key, vendor_name)

    logger.info(
        f"FOIR limit for {co_applicant_details.get('co_applicant_occupation', 'Salaried')}: {foir_limit*100}%"
    )

    # Existing EMI
    existing_emi = (
        co_applicant_details.get("co_applicant_existing_loan_emi_amount", {}).get(
            "amount", 0
        )
        if isinstance(
            co_applicant_details.get("co_applicant_existing_loan_emi_amount"), dict
        )
        else 0
    )
    logger.info(
        f"Existing EMI: {format_amount(existing_emi)} INR for vendor {vendor_name}"
    )

    # Interest rate
    interest_rate_key = (
        "interest_rate_secured"
        if loan_preference == "Secured"
        else "interest_rate_unsecured"
    )
    interest_rate = interest_rate or vendor.get("criteria", {}).get(
        interest_rate_key, 10.0
    )
    if interest_rate == 10.0 and interest_rate_key not in vendor.get("criteria", {}):
        logger.warning(
            f"No {interest_rate_key} found for vendor {vendor_name}, using default 10%"
        )

    try:
        if isinstance(interest_rate, str):
            rate_str = (
                interest_rate.replace("–", "-")
                .split("%")[0]
                .split(" to ")[0]
                .split("-")[0]
                .strip()
            )
            interest_rate = float(rate_str)
        elif isinstance(interest_rate, list):
            rate_str = (
                list(interest_rate[0].values())[0]
                .replace("–", "-")
                .split("%")[0]
                .split(" to ")[0]
                .split("-")[0]
            )
            interest_rate = float(rate_str)
        else:
            interest_rate = float(interest_rate)
        interest_rate = min(max(interest_rate, 5.0), 20.0)
        logger.info("Interest rate: %.2f%%", interest_rate)
    except (ValueError, AttributeError, TypeError, IndexError) as e:

        logger.error("Error parsing interest rate for vendor %s: %s, error: %s, using default 10%%", vendor_name, interest_rate, str(e))
        interest_rate = 10.0

    tenure_years = tenure_years or criteria.get("loan_tenor_years", 15)

        logger.error(
            f"Error parsing interest rate for vendor {vendor_name}: {interest_rate}, error: {str(e)}, using default 10%"
        )
        interest_rate = 10.0

    # Tenure
    tenure_years = tenure_years or vendor.get("criteria", {}).get(
        "loan_tenor_years", 15
    )

    try:
        if isinstance(tenure_years, str):
            tenure_years = float(tenure_years.strip().split(" to ")[0].split()[0])
        tenure_years = min(max(tenure_years, 1.0), 20.0)
        logger.info("Initial tenure: %.1f years", tenure_years)
    except (ValueError, AttributeError) as e:

        logger.error("Error parsing tenure years for vendor %s: %s, error: %s, using default 15 years", vendor_name, tenure_years, str(e))
        tenure_years = 15.0

    min_loan_inr = criteria.get("min_loan_inr", 0) or 0

        logger.error(
            f"Error parsing tenure years for vendor {vendor_name}: {tenure_years}, error: {str(e)}, using default 15 years"
        )
        tenure_years = 15.0

    # Minimum loan
    min_loan_inr = vendor.get("criteria", {}).get("min_loan_inr", 0) or 0
    cibil_score = student_profile.get("loan_details", {}).get("cibil_score", "None")
    bank_balance = co_applicant_details.get("bank_balance", False)
    min_loan_eligible = requested_loan_amount
    if (
        monthly_income > 60000
        and not co_applicant_details.get("co_applicant_existing_loan", "No") == "Yes"
    ):
        min_loan_eligible = max(min_loan_eligible, 7000000)
    if (
        isinstance(cibil_score, str)
        and cibil_score.isdigit()
        and int(cibil_score) >= 700
        and bank_balance
    ):
        min_loan_eligible = max(min_loan_eligible, 10000000)
    if requested_loan_amount < min_loan_inr:
        logger.warning(
            f"Requested loan {format_amount(requested_loan_amount)} INR below minimum {format_amount(min_loan_inr)} for vendor {vendor_name}"
        )
        return (
            0,
            requested_loan_amount,
            f"Loan amount below minimum {format_amount(min_loan_inr)}",
        )


    monthly_rate = interest_rate / (12 * 100)
    tenure_months = tenure_years * 12
    adjusted_loan = requested_loan_amount
    foir = 0
    message = "Loan amount within FOIR limit"
    proposed_emi = 0

    try:
        if total_yearly_income == 0:

            logger.info("No FOIR calculation needed for vendor %s (no income or not required)", vendor_name)
            return 0, requested_loan_amount, "No FOIR calculation needed"

        # Get max loan limit
        max_loan_limit = criteria.get("max_secured_loan_inr", 0) if loan_preference == "Secured" else criteria.get("max_unsecured_loan_inr", 0)
        if criteria.get("max_unsecured_loan_usd") and loan_preference == "Unsecured":
            max_loan_limit = criteria.get("max_unsecured_loan_usd") * (exchange_rate or get_usd_to_inr_rate())

        # Check for Master's degree and PSI option
        intended_degree = education_details.get("intended_degree", "")
        repayment_options = criteria.get("repayment_options", [])
        cibil_score = loan_details.get("cibil_score", "None")
        is_masters = intended_degree.lower() == "master's"
        has_psi = "PSI" in repayment_options
        cibil_good = isinstance(cibil_score, str) and cibil_score.isdigit() and int(cibil_score) >= 700

        if is_masters and has_psi:
            # During moratorium, cap interest at Rs 5000
            moratorium_partial_emi = 5000.0
            total_obligations_moratorium = existing_emi + moratorium_partial_emi
            foir_moratorium = (total_obligations_moratorium / monthly_income * 100) if monthly_income > 0 else float('inf')
            logger.info("Master's with PSI: Moratorium partial EMI Rs 5000, FOIR: %.2f%% (limit: %.1f%%)", foir_moratorium, foir_limit*100)
            
            if foir_moratorium <= foir_limit * 100:
                # If moratorium FOIR is okay, check full EMI for post-moratorium
                full_emi = requested_loan_amount * monthly_rate * (1 + monthly_rate) ** tenure_months / ((1 + monthly_rate) ** tenure_months - 1) if monthly_rate > 0 else requested_loan_amount / tenure_months
                full_emi = round(full_emi, 2)
                total_obligations_full = existing_emi + full_emi
                foir_full = (total_obligations_full / monthly_income * 100) if monthly_income > 0 else float('inf')
                logger.info("Full EMI: %s INR, FOIR: %.2f%% (limit: %.1f%%)", format_amount(full_emi), foir_full, foir_limit*100)
                
                if cibil_good:
                    # If CIBIL good, offer up to max limit
                    adjusted_loan = min(requested_loan_amount, max_loan_limit)
                    foir = foir_moratorium  # Use moratorium FOIR for scoring
                    message = f"Master's with PSI and good CIBIL: Loan up to max limit {format_amount(max_loan_limit)}; Capped at requested amount {format_amount(adjusted_loan)}"
                    if adjusted_loan < requested_loan_amount:
                        message += " (exceeds max limit)"
                else:
                    # Standard FOIR adjustment
                    if foir_full <= foir_limit * 100:
                        adjusted_loan = requested_loan_amount
                        foir = foir_full
                    else:
                        max_obligations = foir_limit * monthly_income
                        max_emi = max_obligations - existing_emi
                        if max_emi <= 0:
                            adjusted_loan = 0
                            foir = float('inf')
                            message = "Existing obligations exceed FOIR limit"
                        else:
                            adjusted_loan = max_emi * ((1 + monthly_rate) ** tenure_months - 1) / (monthly_rate * (1 + monthly_rate) ** tenure_months) if monthly_rate > 0 else max_emi * tenure_months
                            adjusted_loan = round(adjusted_loan, 2)
                            foir = (existing_emi + max_emi) / monthly_income * 100 if monthly_income > 0 else float('inf')
                            message = f"Loan adjusted to INR {format_amount(adjusted_loan)} to meet FOIR limit ({foir_limit*100}%)"
            else:
                # Moratorium FOIR exceeds limit
                adjusted_loan = 0
                foir = foir_moratorium
                message = "Moratorium partial interest exceeds FOIR limit"
        else:
            # Standard FOIR calculation
            proposed_emi = adjusted_loan * monthly_rate * (1 + monthly_rate) ** tenure_months / ((1 + monthly_rate) ** tenure_months - 1) if monthly_rate > 0 else adjusted_loan / tenure_months
            proposed_emi = round(proposed_emi, 2)
            total_obligations = existing_emi + proposed_emi
            foir = (total_obligations / monthly_income * 100) if monthly_income > 0 else float('inf')
            logger.info("Initial EMI: %s INR, FOIR: %.2f%% (limit: %.1f%%)", format_amount(proposed_emi), foir, foir_limit*100)

            if foir > foir_limit * 100:
                min_tenure_years = max(1.0, tenure_years - 5)
                tenure_years_adjusted = tenure_years
                while tenure_years_adjusted >= min_tenure_years and foir > foir_limit * 100:
                    tenure_years_adjusted -= 1
                    tenure_months = tenure_years_adjusted * 12
                    proposed_emi = adjusted_loan * monthly_rate * (1 + monthly_rate) ** tenure_months / ((1 + monthly_rate) ** tenure_months - 1) if monthly_rate > 0 else adjusted_loan / tenure_months
                    proposed_emi = round(proposed_emi, 2)
                    total_obligations = existing_emi + proposed_emi
                    foir = (total_obligations / monthly_income * 100) if monthly_income > 0 else float('inf')
                    logger.info("Adjusted tenure to %.1f years: EMI %s INR, FOIR %.2f%%", tenure_years_adjusted, format_amount(proposed_emi), foir)

                if foir <= foir_limit * 100:
                    message = f"Tenure adjusted to {tenure_years_adjusted} years to meet FOIR limit ({foir_limit*100}%)"
                    logger.info(message)
                else:
                    max_obligations = foir_limit * monthly_income
                    max_emi = max_obligations - existing_emi
                    if max_emi <= 0:
                        logger.warning("Existing obligations exceed FOIR limit for vendor %s", vendor_name)
                        adjusted_loan = 0
                        message = "Existing obligations exceed FOIR limit"
                    else:
                        adjusted_loan = max_emi * ((1 + monthly_rate) ** tenure_months - 1) / (monthly_rate * (1 + monthly_rate) ** tenure_months) if monthly_rate > 0 else max_emi * tenure_months
                        adjusted_loan = round(adjusted_loan, 2)
                        proposed_emi = max_emi
                        foir = (existing_emi + proposed_emi) / monthly_income * 100 if monthly_income > 0 else float('inf')
                        message = f"Loan adjusted to INR {format_amount(adjusted_loan)} to meet FOIR limit ({foir_limit*100}%)"

        if adjusted_loan < min_loan_inr:
            logger.warning("Adjusted loan %s INR below minimum %s for vendor %s", format_amount(adjusted_loan), format_amount(min_loan_inr), vendor_name)
            return foir, adjusted_loan, f"Adjusted loan {format_amount(adjusted_loan)} below minimum {format_amount(min_loan_inr)}"

            logger.info(
                f"No FOIR calculation needed for vendor {vendor_name} (no income or not required)"
            )
            return 0, requested_loan_amount, "No FOIR calculation needed"

        # Initial EMI
        proposed_emi = (
            adjusted_loan
            * monthly_rate
            * (1 + monthly_rate) ** tenure_months
            / ((1 + monthly_rate) ** tenure_months - 1)
            if monthly_rate > 0
            else adjusted_loan / tenure_months
        )
        proposed_emi = round(proposed_emi, 2)
        total_obligations = existing_emi + proposed_emi
        foir = (
            (total_obligations / monthly_income * 100)
            if monthly_income > 0
            else float("inf")
        )
        logger.info(
            f"Initial EMI: {format_amount(proposed_emi)} INR, FOIR: {foir:.2f}% (limit: {foir_limit*100}%)"
        )

        if foir > foir_limit * 100:
            min_tenure_years = max(1.0, tenure_years - 5)
            tenure_years_adjusted = tenure_years
            while tenure_years_adjusted >= min_tenure_years and foir > foir_limit * 100:
                tenure_years_adjusted -= 1
                tenure_months = tenure_years_adjusted * 12
                proposed_emi = (
                    adjusted_loan
                    * monthly_rate
                    * (1 + monthly_rate) ** tenure_months
                    / ((1 + monthly_rate) ** tenure_months - 1)
                    if monthly_rate > 0
                    else adjusted_loan / tenure_months
                )
                proposed_emi = round(proposed_emi, 2)
                total_obligations = existing_emi + proposed_emi
                foir = (
                    (total_obligations / monthly_income * 100)
                    if monthly_income > 0
                    else float("inf")
                )
                logger.info(
                    f"Adjusted tenure to {tenure_years_adjusted} years: EMI {format_amount(proposed_emi)} INR, FOIR {foir:.2f}%"
                )

            if foir <= foir_limit * 100:
                message = f"Tenure adjusted to {tenure_years_adjusted} years to meet FOIR limit ({foir_limit*100}%)"
                logger.info(message)
            else:
                max_obligations = foir_limit * monthly_income
                max_emi = max_obligations - existing_emi
                if max_emi <= 0:
                    logger.warning(
                        f"Existing obligations exceed FOIR limit for vendor {vendor_name}"
                    )
                    return foir, 0, "Existing obligations exceed FOIR limit"
                adjusted_loan = (
                    max_emi
                    * ((1 + monthly_rate) ** tenure_months - 1)
                    / (monthly_rate * (1 + monthly_rate) ** tenure_months)
                    if monthly_rate > 0
                    else max_emi * tenure_months
                )
                adjusted_loan = round(max(adjusted_loan, min_loan_eligible), 2)

                if adjusted_loan < min_loan_inr:
                    logger.warning(
                        f"Adjusted loan {format_amount(adjusted_loan)} INR below minimum {format_amount(min_loan_inr)} for vendor {vendor_name}"
                    )
                    return (
                        foir,
                        adjusted_loan,
                        f"Adjusted loan {format_amount(adjusted_loan)} below minimum {format_amount(min_loan_inr)}",
                    )

                proposed_emi = max_emi
                foir = (
                    (existing_emi + proposed_emi) / monthly_income * 100
                    if monthly_income > 0
                    else float("inf")
                )
                message = f"Loan adjusted to INR {format_amount(adjusted_loan)} to meet FOIR limit ({foir_limit*100}%)"
                logger.info(message)


        return foir, adjusted_loan, message
    except Exception as e:
        logger.error("Error calculating FOIR for vendor %s: %s", vendor_name, str(e))
        return 0, requested_loan_amount, f"Error calculating FOIR: {str(e)}"


def normalize_loan_options(options):
    """Normalize loan_options to a list of individual options."""
    if not options:
        return ["Secured", "Unsecured"]
    if isinstance(options, str):
        return [opt.strip() for opt in options.replace("&", ",").split(",")]
    if isinstance(options, list):
        flattened = []
        for opt in options:
            if isinstance(opt, dict):
                flattened.extend(list(opt.keys()))
            elif isinstance(opt, str):
                flattened.extend([o.strip() for o in opt.replace("&", ",").split(",")])
        return flattened
    return ["Secured", "Unsecured"]


def check_country_eligibility(vendor: Dict, country: str) -> bool:
    """Check if vendor supports the destination country."""
    criteria = vendor.get("criteria", {})
    supported_countries = criteria.get("supported_countries", [])
    
    if not supported_countries:
        return True
    
    return country in supported_countries or "All countries" in supported_countries

def check_geo_restrictions(vendor: Dict, geo_state: str) -> bool:
    """Check if vendor has geographical restrictions for the state."""
    criteria = vendor.get("criteria", {})
    geo_restrictions = criteria.get("geographical_restrictions", [])
    
    if not geo_restrictions:
        return True
    
    return not any(geo_state.upper() in restriction.upper() for restriction in geo_restrictions)

def check_degree_eligibility(vendor: Dict, intended_degree: str) -> bool:
    """Check if vendor supports the intended degree."""
    if not intended_degree:
        return True
    
    criteria = vendor.get("criteria", {})
    supported_degrees = criteria.get("supported_degrees", [])
    
    if not supported_degrees:
        return True
    
    return intended_degree in supported_degrees

def check_loan_amount_eligibility(vendor: Dict, loan_amount: float, loan_preference: str) -> Tuple[bool, str, str]:
    """Check if loan amount is within vendor limits."""
    criteria = vendor.get("criteria", {})
    
    # Get maximum limits
    max_unsecured_inr = criteria.get("max_unsecured_loan_inr")
    max_unsecured_usd = criteria.get("max_unsecured_loan_usd")
    if max_unsecured_usd:
        max_unsecured_inr = max_unsecured_usd * get_usd_to_inr_rate()
    max_secured_inr = criteria.get("max_secured_loan_inr")
    
    # Check eligibility based on loan preference
    if loan_preference == "Secured":
        if max_secured_inr and loan_amount <= max_secured_inr:
            return True, "Secured", "Meets max secured loan limit"
        elif max_unsecured_inr and loan_amount <= max_unsecured_inr:
            return True, "Unsecured", "Exceeds secured limit but qualifies for unsecured"
        else:
            return False, loan_preference, f"Exceeds maximum loan limits (Secured: {format_amount(max_secured_inr or 0)}, Unsecured: {format_amount(max_unsecured_inr or 0)})"
    else:  # Unsecured
        if max_unsecured_inr and loan_amount <= max_unsecured_inr:
            return True, "Unsecured", "Meets max unsecured loan limit"
        else:
            return False, loan_preference, f"Exceeds max unsecured loan limit: {format_amount(max_unsecured_inr or 0)}"

def check_cibil_eligibility(vendor: Dict, cibil_score: str) -> bool:
    """Check if CIBIL score meets vendor requirements."""
    criteria = vendor.get("criteria", {})
    cibil_requirement = criteria.get("cibil_score_requirement", "None")
    
    if cibil_requirement == "None" or "preferred" in cibil_requirement.lower():
        return True
    
    if not isinstance(cibil_score, str) or not cibil_score.isdigit():
        return False
    
    if cibil_requirement.replace("preferred", "").replace("+", "").isdigit():
        required_score = int(cibil_requirement.split("+")[0])
        return int(cibil_score) >= required_score
    
    return False

def check_loan_type_eligibility(vendor: Dict, loan_preference: str) -> bool:
    """Check if vendor supports the loan type."""
    criteria = vendor.get("criteria", {})
    loan_options = normalize_loan_options(criteria.get("loan_options", []))
    return loan_preference in loan_options

def check_co_applicant_eligibility(vendor: Dict, co_applicant_available: bool, co_applicant_relation: str) -> bool:
    """Check co-applicant requirements."""
    criteria = vendor.get("criteria", {})
    
    if criteria.get("requires_co_applicant"):
        if not co_applicant_available:
            return False
        
        supported_relations = criteria.get("supported_co_applicant_relations", [])
        if supported_relations and co_applicant_relation and co_applicant_relation not in supported_relations:
            return False
    
    return True

def check_collateral_eligibility(vendor: Dict, loan_preference: str, collateral_available: bool) -> bool:
    """Check collateral requirements."""
    criteria = vendor.get("criteria", {})
    requires_collateral = criteria.get("requires_collateral")
    
    if requires_collateral is None:
        requires_collateral = True if loan_preference == "Secured" else False
    
    if requires_collateral and not collateral_available:
        return False
    
    return True

def check_own_house_requirement(vendor: Dict, own_house: bool) -> bool:
    """Check own house requirement."""
    vendor_name = vendor.get("vendorName")
    criteria = vendor.get("criteria", {})
    
    # Exempted vendors
    exempted_vendors = ["HDFC Credila", "Avanse", "Auxilo", "Avanse Global", "Prodigy", "Mpower"]
    
    if vendor_name in exempted_vendors:
        return True
    
    if criteria.get("own_house_required") and not own_house:
        return False
    
    return True

def check_admission_status_eligibility(vendor: Dict, admission_status: str, english_test: Dict, standardized_test: Dict) -> bool:
    """Check admission status and test score requirements."""
    vendor_name = vendor.get("vendorName")
    criteria = vendor.get("criteria", {})
    
    # HDFC Credila allows any admission status
    if vendor_name == "HDFC Credila":
        return True
    
    # Special handling for conditional admission with test scores
    if vendor_name in ["HDFC Credila", "IDFC Bank", "Yes Bank"] and admission_status == "Conditional letter received":
        english_test_type = english_test.get("type") if isinstance(english_test, dict) else None
        english_test_score = english_test.get("score") if isinstance(english_test, dict) else None
        standardized_test_score = standardized_test.get("score") if isinstance(standardized_test, dict) else None
        
        # Check English test requirements
        if english_test_score is not None:
            if english_test_type == "IELTS" and english_test_score < criteria.get("min_ielts_score", float('inf')):
                return False
            elif english_test_type == "TOEFL" and english_test_score < criteria.get("min_toefl_score", float('inf')):
                return False
        
        # Check standardized test requirements
        if standardized_test_score is not None and standardized_test_score < criteria.get("min_gmat_score", float('inf')):
            return False
        
        return True
    
    # General admission status check
    requires_admission = criteria.get("requires_admission")
    
    if isinstance(requires_admission, bool):
        if requires_admission and admission_status not in ["Admission letter received", "Conditional letter received"]:
            return False
    elif isinstance(requires_admission, list):
        requires_letter = any(
            entry.get("Admission Letter") or entry.get("Conditional Admission")
            for entry in requires_admission
        )
        if requires_letter and admission_status not in ["Admission letter received", "Conditional letter received"]:
            return False
    
    return True

def calculate_vendor_score(vendor: Dict, student_profile: Dict, loan_preference: str, university_vendors: List[str], no_university_vendors: bool, foir_results: Dict) -> int:
    """Calculate matching score for a vendor based on various criteria."""
    vendor_name = vendor.get("vendorName")
    criteria = vendor.get("criteria", {})
    score = 0
    
    # Extract profile details
    education_details = student_profile.get("education_details", {})
    loan_details = student_profile.get("loan_details", {})
    co_applicant_details = student_profile.get("co_applicant_details", {})
    
    university = education_details.get("university_name", [""])[0] if isinstance(education_details.get("university_name"), list) else ""
    country = education_details.get("study_destination_country", [""])[0] if isinstance(education_details.get("study_destination_country"), list) else ""
    course_type = education_details.get("course_type", "").replace("-", "")
    admission_status = education_details.get("admission_status", "")
    academic_score = education_details.get("academic_score", {}).get("value", 0)
    if academic_score == 0:
        academic_score = education_details.get("marks_12th", {}).get("value", education_details.get("marks_10th", {}).get("value", 0))
    backlogs = education_details.get("educational_backlogs", 0)
    age = (datetime.utcnow().year - int(student_profile.get("date_of_birth", "2000-01-01")[:4])) if student_profile.get("date_of_birth") else None
    cibil_score = loan_details.get("cibil_score", "None")
    co_applicant_occupation = co_applicant_details.get("co_applicant_occupation", "")
    co_applicant_income = co_applicant_details.get("co_applicant_income_amount", {}).get("amount", 0) if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict) else 0
    collateral_available = loan_details.get("collateral_available") == "Yes"
    co_applicant_available = loan_details.get("co_applicant_available") == "Yes"
    english_test = education_details.get("english_test", {})
    standardized_test = education_details.get("standardized_test", {})
    bank_balance = co_applicant_details.get("bank_balance", False)
    
    # Loan amount
    loan_amount_dict = loan_details.get("loan_amount_requested", education_details.get("loan_amount_requested", {}))
    loan_amount = loan_amount_dict.get("amount", 0) if isinstance(loan_amount_dict, dict) else 0
    
    # University Vendor List (20 points)
    no_university_list_vendors = ["HDFC Credila", "Auxilo", "Avanse", "Tata Capital", "InCred"]
    if vendor_name in no_university_list_vendors or any(vendor_name.lower().replace("-", "") == uv.lower().replace("-", "") for uv in university_vendors):
        score += 20
    
    # Loan Amount after FOIR (15 points)
    foir_result = foir_results.get((vendor_name, loan_preference), {})
    adjusted_loan = foir_result.get("adjusted_loan", loan_amount)
    if adjusted_loan == loan_amount:
        score += 15
    elif adjusted_loan > 0 and abs(adjusted_loan - loan_amount) / loan_amount <= 0.1:
        score += 7
    
    # Supported Country (10 points)
    if check_country_eligibility(vendor, country):
        score += 10
    
    # Supported Course Type (10 points)
    supported_courses = [c.replace("-", "") for c in criteria.get("supported_courses", [])]
    if not supported_courses or course_type.lower() in [sc.lower() for sc in supported_courses]:
        score += 10
    
    # Collateral (8 points)
    if collateral_available and loan_preference == "Secured":
        score += 8
    
    # Loan Type (7 points)
    if check_loan_type_eligibility(vendor, loan_preference):
        if loan_preference == "Secured" and collateral_available:
            score += 7
        elif loan_preference == "Unsecured":
            score += 7
    
    # Admission Status (5 points)
    if vendor_name == "HDFC Credila":
        score += 5
    elif check_admission_status_eligibility(vendor, admission_status, english_test, standardized_test):
        if admission_status in ["Admission letter received", "Conditional letter received"]:
            score += 5
    
    # Co-Applicant Salaried (3 points)
    if co_applicant_available and criteria.get("requires_co_applicant") and co_applicant_occupation == "Salaried":
        score += 3
    
    # FOIR Score (2 points)
    foir_value = foir_result.get("foir", 0)
    monthly_income = co_applicant_income / 12 if co_applicant_income > 0 else 0
    foir_limit = 75 if monthly_income >= 100000 else 60
    if foir_value <= foir_limit:
        score += 2
    
    # Academic Score (5 points)
    min_academic_score = criteria.get("min_academic_score_percentage")
    if not min_academic_score or academic_score >= min_academic_score:
        score += 5
    
    # English Test Score (3 points)
    english_test_type = english_test.get("type") if isinstance(english_test, dict) else None
    english_test_score = english_test.get("score") if isinstance(english_test, dict) else None
    if english_test_score is not None:
        if english_test_type == "IELTS" and english_test_score >= criteria.get("min_ielts_score", 0):
            score += 3
        elif english_test_type == "TOEFL" and english_test_score >= criteria.get("min_toefl_score", 0):
            score += 3
    elif not criteria.get("min_ielts_score") and not criteria.get("min_toefl_score"):
        score += 3
    
    # Standardized Test Score (2 points)
    standardized_test_score = standardized_test.get("score") if isinstance(standardized_test, dict) else None
    if standardized_test_score is not None and standardized_test_score >= criteria.get("min_gmat_score", 0):
        score += 2
    elif not criteria.get("min_gmat_score"):
        score += 2
    
    # Backlogs (5 points)
    max_backlogs = criteria.get("max_educational_backlogs")
    if max_backlogs is None or backlogs <= max_backlogs:
        score += 5
    
    # Age (2 points)
    max_age = criteria.get("max_student_age")
    if max_age is None or (age and age <= max_age):
        score += 2
    
    # Margin Money (2 points) - assuming met if not specified
    if not criteria.get("margin_money_percentage") or criteria.get("margin_money_percentage") == 0:
        score += 2
    
    # CIBIL Score (1 point)
    if check_cibil_eligibility(vendor, cibil_score):
        score += 1
    
    return score

def perform_strict_matching(vendors: List[Dict], student_profile: Dict, loan_amount: float, loan_types: List[str]) -> List[Tuple[Dict, str]]:
    """Perform strict matching based on mandatory criteria."""
    eligible_vendors = []
    seen = set()  # To avoid duplicates
    
    # Extract profile details
    education_details = student_profile.get("education_details", {})
    loan_details = student_profile.get("loan_details", {})
    co_applicant_details = student_profile.get("co_applicant_details", {})
    
    country = education_details.get("study_destination_country", [""])[0] if isinstance(education_details.get("study_destination_country"), list) else ""
    geo_state = student_profile.get("current_location_state", "").upper()
    intended_degree = education_details.get("intended_degree", "")
    admission_status = education_details.get("admission_status", "")
    cibil_score = loan_details.get("cibil_score", "None")
    co_applicant_available = loan_details.get("co_applicant_available") == "Yes"
    co_applicant_relation = co_applicant_details.get("co_applicant_relation", "")
    collateral_available = loan_details.get("collateral_available") == "Yes"
    collateral_value = loan_details.get("collateral_value_amount", {}).get("amount") if isinstance(loan_details.get("collateral_value_amount"), dict) else None
    collateral_existing_loan = loan_details.get("collateral_existing_loan", "No") == "No"
    own_house = student_profile.get("own_house", False)
    english_test = education_details.get("english_test", {})
    standardized_test = education_details.get("standardized_test", {})
    
    for loan_preference in loan_types:
        logger.info(f"### Evaluating {loan_preference} Loans")
        
        # Filter vendors by country and geo restrictions
        filtered_vendors = []
        for vendor in vendors:
            vendor_name = vendor.get("vendorName")
            
            if not check_country_eligibility(vendor, country):
                logger.info(f"Vendor {vendor_name} filtered: country not supported")
                continue
            
            if not check_geo_restrictions(vendor, geo_state):
                logger.info(f"Vendor {vendor_name} filtered: geo restrictions")
                continue
            
            filtered_vendors.append(vendor)
        
        # Strict matching on filtered vendors
        for vendor in filtered_vendors:
            vendor_name = vendor.get("vendorName")
            reasons = []
            is_eligible = True
            effective_loan_type = loan_preference
            
            logger.info(f"{vendor_name}:")
            
            # Degree check
            if not check_degree_eligibility(vendor, intended_degree):
                reasons.append(f"Intended degree {intended_degree} not supported")
                is_eligible = False
                logger.info(f"  - Supported Degree: No")
            else:
                logger.info(f"  - Supported Degree: Yes")
            
            # Loan amount check
            amount_eligible, effective_type, amount_message = check_loan_amount_eligibility(vendor, loan_amount, loan_preference)
            if not amount_eligible:
                reasons.append(amount_message)
                is_eligible = False
                logger.info(f"  - Loan Amount: {amount_message}")
            else:
                effective_loan_type = effective_type
                logger.info(f"  - Loan Amount: {amount_message}")
                
                # Special case: if collateral value is less than loan amount, switch to unsecured
                if (loan_preference == "Secured" and collateral_existing_loan and 
                    collateral_value and loan_amount < collateral_value):
                    effective_loan_type = "Unsecured"
                    logger.info(f"  - Adjusted to Unsecured due to collateral value")
            
            # CIBIL score check
            if not check_cibil_eligibility(vendor, cibil_score):
                reasons.append(f"CIBIL score {cibil_score} does not meet requirements")
                is_eligible = False
                logger.info(f"  - CIBIL Score: Does not meet requirement")
            else:
                logger.info(f"  - CIBIL Score: Meets requirement")
            
            # Loan type check
            if not check_loan_type_eligibility(vendor, effective_loan_type):
                reasons.append(f"Loan preference {effective_loan_type} not supported")
                is_eligible = False
                logger.info(f"  - Loan Preference: Does not match {effective_loan_type.lower()}")
            else:
                logger.info(f"  - Loan Preference: Matches {effective_loan_type.lower()}")
            
            # Co-applicant check
            if not check_co_applicant_eligibility(vendor, co_applicant_available, co_applicant_relation):
                reasons.append("Co-applicant requirements not met")
                is_eligible = False
                logger.info(f"  - Co-Applicant: Requirements not met")
            else:
                logger.info(f"  - Co-Applicant: {'Available' if co_applicant_available else 'Not required'}")
            
            # Collateral check
            if not check_collateral_eligibility(vendor, effective_loan_type, collateral_available):
                reasons.append("Collateral required but not available")
                is_eligible = False
                logger.info(f"  - Collateral: Required but not available")
            else:
                logger.info(f"  - Collateral: {'Available' if collateral_available else 'Not required'}")
            
            # Own house check
            if not check_own_house_requirement(vendor, own_house):
                reasons.append("Own house required but not provided")
                is_eligible = False
                logger.info(f"  - Own House: Required but not provided")
            else:
                logger.info(f"  - Own House: Requirement satisfied")
            
            # Admission status check
            if not check_admission_status_eligibility(vendor, admission_status, english_test, standardized_test):
                reasons.append("Admission status or test scores do not meet requirements")
                is_eligible = False
                logger.info(f"  - Admission Status: Requirements not met")
            else:
                logger.info(f"  - Admission Status: Requirements met")
            
            if is_eligible:
                key = (vendor_name, effective_loan_type)
                if key not in seen:
                    seen.add(key)
                    eligible_vendors.append((vendor, effective_loan_type))
                    logger.info(f"  - Match: Yes")
            else:
                logger.info(f"  - Match: No ({', '.join(reasons)})")
    
    return eligible_vendors

def get_function_based_vendor_matches(student_profile: Dict, vendors: Optional[List[Dict]] = None) -> Tuple[List[Dict], Optional[str]]:
    """Match student profile with university-specific vendors using function-based logic."""
    try:
        student_id = student_profile.get("student_id", "?")
        logger.info(f"Starting function-based vendor matching for student {student_id}")
        


# Match student profile with university-specific vendors using OpenAI GPT-4 or mock response.
def get_llm_vendor_matches(
    student_profile: Dict, vendors: Optional[List[Dict]] = None
) -> Tuple[List[Dict], Optional[str]]:
    """Match student profile with university-specific vendors using OpenAI GPT-4 or mock response."""
    try:
        student_id = student_profile.get("student_id", "?")
        logger.info(f"Starting vendor matching for student {student_id}")
        logger.debug(
            f"Raw student profile: {json.dumps(student_profile, default=str, ensure_ascii=False)}"
        )


        # Validate profile
        student_profile = validate_profile(student_profile)

        # Validate co-applicant details
        if student_profile.get("loan_details", {}).get(
            "co_applicant_available"
        ) == "Yes" and not student_profile.get("co_applicant_details"):
            logger.warning(
                "Co-applicant details missing despite co_applicant_available: Yes"
            )
            student_profile["co_applicant_details"] = {
                "co_applicant_occupation": "Salaried",
                "co_applicant_relation": "Unknown",
            }

        # Extract profile details
        education_details = student_profile.get("education_details", {})
        loan_details = student_profile.get("loan_details", {})
        co_applicant_details = student_profile.get("co_applicant_details", {})

        
        university = education_details.get("university_name", [""])[0] if isinstance(education_details.get("university_name"), list) else ""
        collateral_available = loan_details.get("collateral_available") == "Yes"
        co_applicant_available = loan_details.get("co_applicant_available") == "Yes"

        # Define key variables
        co_applicant_available = loan_details.get("co_applicant_available") == "Yes"
        collateral_available = loan_details.get("collateral_available") == "Yes"
        university = (
            education_details.get("university_name", [""])[0]
            if isinstance(education_details.get("university_name"), list)
            else ""
        )
        country = (
            education_details.get("study_destination_country", [""])[0]
            if isinstance(education_details.get("study_destination_country"), list)
            else ""
        )
        geo_state = student_profile.get("current_location_state", "").upper()
        course_type = education_details.get("course_type", "").replace("-", "")
        intended_degree = education_details.get("intended_degree", "")
        admission_status = education_details.get("admission_status", "")
        academic_score = education_details.get("academic_score", {}).get("value", 0)
        if academic_score == 0:
            academic_score = education_details.get("marks_12th", {}).get(
                "value", education_details.get("marks_10th", {}).get("value", 0)
            )
        backlogs = education_details.get("educational_backlogs", 0)
        age = (
            (
                datetime.utcnow().year
                - int(student_profile.get("date_of_birth", "2000-01-01")[:4])
            )
            if student_profile.get("date_of_birth")
            else None
        )
        cibil_score = loan_details.get("cibil_score", "None")
        co_applicant_occupation = co_applicant_details.get(
            "co_applicant_occupation", ""
        )
        co_applicant_relation = co_applicant_details.get("co_applicant_relation", "")
        co_applicant_income = (
            co_applicant_details.get("co_applicant_income_amount", {}).get("amount", 0)
            if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict)
            else 0
        )
        english_test = education_details.get("english_test", {})
        english_test_type = (
            english_test.get("type") if isinstance(english_test, dict) else None
        )
        english_test_score = (
            english_test.get("score") if isinstance(english_test, dict) else None
        )
        standardized_test = education_details.get("standardized_test", {})
        standardized_test_type = (
            standardized_test.get("type")
            if isinstance(standardized_test, dict)
            else None
        )
        standardized_test_score = (
            standardized_test.get("score")
            if isinstance(standardized_test, dict)
            else None
        )
        course_duration = education_details.get("course_duration", {})
        course_duration_years = (
            float(course_duration.get("years", 0))
            + (float(course_duration.get("months", 0)) / 12)
            if isinstance(course_duration, dict)
            else 0.0
        )
        collateral_type = loan_details.get("collateral_type")
        collateral_value = (
            loan_details.get("collateral_value_amount", {}).get("amount")
            if isinstance(loan_details.get("collateral_value_amount"), dict)
            else None
        )
        collateral_location_state = loan_details.get("collateral_location_state")
        collateral_existing_loan = (
            loan_details.get("collateral_existing_loan", "No") == "No"
        )
        own_house = student_profile.get("own_house", False)
        bank_balance = co_applicant_details.get("bank_balance", False)


        # Vendors ignoring university list
        NO_UNIVERSITY_LIST_VENDORS = [
            "HDFC Credila",
            "Auxilo",
            "Avanse",
            "Tata Capital",
            "InCred",
        ]

        valid_vendors = VENDORS if vendors is None else vendors
        no_university_vendors = False
        university_vendors = []
        
        if university and universities_collection is not None:
            try:
                university_doc = universities_collection.find_one(
                    {"name": {"$regex": f"^{re.escape(university)}$", "$options": "i"}}
                )
                if (
                    university_doc
                    and "vendors" in university_doc
                    and university_doc["vendors"]
                ):
                    university_vendors = university_doc["vendors"]
                    logger.info(
                        f"Found vendors for university {university}: {university_vendors}"
                    )
                    valid_vendors = [
                        v
                        for v in valid_vendors
                        if v["vendorName"] in NO_UNIVERSITY_LIST_VENDORS
                        or any(
                            v["vendorName"].lower().replace("-", "")
                            == uv.lower().replace("-", "")
                            for uv in university_vendors
                        )
                    ]
                    logger.info(
                        f"Filtered to {len(valid_vendors)} university-specific vendors: {[v['vendorName'] for v in valid_vendors]}"
                    )
                else:
                    logger.warning(
                        f"No vendors found for university {university} in MongoDB; using all vendors with exemptions"
                    )
                    no_university_vendors = True
            except Exception as e:
                logger.error(
                    f"Error querying MongoDB for university {university}: {str(e)}"
                )
                no_university_vendors = True

        if not valid_vendors:
            logger.error("No vendors available for matching")
            return [], "No vendors configured"

        # Convert loan amount
        try:
            loan_amount_dict = loan_details.get("loan_amount_requested", education_details.get("loan_amount_requested", {}))
            if not isinstance(loan_amount_dict, dict):
                logger.error(f"Invalid loan_amount_requested structure: {loan_amount_dict}")
                raise ValueError("loan_amount_requested must be a dictionary")
            
            raw_amount = loan_amount_dict.get("amount")
            currency = loan_amount_dict.get("currency", "INR")
            
            if raw_amount is None or raw_amount <= 0:
                logger.error(f"Invalid loan amount: {raw_amount}")
                raise ValueError("Loan amount must be positive")
            
            loan_amount = float(raw_amount)
            
            if currency == "USD":
                exchange_rate = get_usd_to_inr_rate()
                loan_amount *= exchange_rate
                logger.info(f"Converted USD {raw_amount} to INR {loan_amount:.2f} (rate: {exchange_rate})")
            

            loan_details = loan_details.get(
                "loan_amount_requested",
                education_details.get("loan_amount_requested", {}),
            )
            if not isinstance(loan_details, dict):
                logger.error(
                    f"Invalid loan_amount_requested structure: {loan_details}, type: {type(loan_details)}"
                )
                raise ValueError("loan_amount_requested must be a dictionary")
            raw_amount = loan_details.get("amount")
            currency = loan_details.get("currency", "INR")
            logger.debug(
                f"Raw loan amount: {raw_amount}, type: {type(raw_amount)}, currency: {currency}"
            )

            if raw_amount is None:
                logger.error("Loan amount is None in loan_amount_requested")
                raise ValueError("Loan amount cannot be None")

            try:
                loan_amount = float(raw_amount)
            except (ValueError, TypeError) as e:
                logger.error(
                    f"Failed to convert loan amount '{raw_amount}' to float: {str(e)}"
                )
                raise ValueError(f"Invalid loan amount format: {raw_amount}")

            if loan_amount <= 0:
                logger.error(f"Loan amount is non-positive: {loan_amount}")
                raise ValueError("Loan amount must be positive")

            if currency == "USD":
                exchange_rate = get_usd_to_inr_rate()
                loan_amount *= exchange_rate
                logger.info(
                    f"Converted USD {loan_amount/exchange_rate:.2f} to INR {loan_amount:.2f} (rate: {exchange_rate})"
                )

            logger.info(f"Final loan amount: {format_amount(loan_amount)} INR")
        except ValueError as e:
            logger.error(f"Error parsing loan amount: {str(e)}")
            return [], f"Failed to parse loan amount: {str(e)}"


        # Determine loan types to evaluate
        loan_types = ["Secured", "Unsecured"] if collateral_available and co_applicant_available else (["Secured"] if collateral_available else ["Unsecured"])
        
        # Perform strict matching
        eligible_vendors = perform_strict_matching(valid_vendors, student_profile, loan_amount, loan_types)
        logger.info(f"Eligible vendors after strict matching: {len(eligible_vendors)} - {[(v['vendorName'], lp) for v, lp in eligible_vendors]}")

        # Evaluate both Secured and Unsecured if applicable
        loan_types = (
            ["Secured", "Unsecured"]
            if collateral_available and co_applicant_available
            else (["Secured"] if collateral_available else ["Unsecured"])
        )
        all_eligible_vendors = []
        foir_results = {}

        for loan_preference in loan_types:
            logger.info(f"### Evaluating {loan_preference} Loans")
            logger.info(
                f"Profile:\n"
                f"  - Dest Country: {country}\n"
                f"  - University: {university}\n"
                f"  - Intended Degree: {intended_degree}\n"
                f"  - Course Category: {course_type}\n"
                f"  - Loan Amount INR: {format_amount(loan_amount)}\n"
                f"  - Collateral Available: {collateral_available}\n"
                f"  - Collateral Type: {collateral_type}\n"
                f"  - Collateral Value INR: {format_amount(collateral_value)}\n"
                f"  - Collateral Location State: {collateral_location_state}\n"
                f"  - Co-Applicant Available: {co_applicant_available}\n"
                f"  - Co-Applicant Relation: {co_applicant_relation}\n"
                f"  - Co-Applicant Occupation: {co_applicant_occupation}\n"
                f"  - Co-Applicant Income INR (Annual): {format_amount(co_applicant_income)}\n"
                f"  - CIBIL Score: {cibil_score}\n"
                f"  - Academic Score %: {academic_score}\n"
                f"  - Age: {age}\n"
                f"  - Backlogs: {backlogs}\n"
                f"  - Admission Status: {admission_status}\n"
                f"  - Loan Preference: {loan_preference}"
            )

            # Filter vendors by country and geo
            logger.info(
                f"Filtering banks for country {country} and geo {geo_state} ({loan_preference})"
            )
            filtered_vendors = []
            for vendor in valid_vendors:
                vendor_name = vendor.get("vendorName")
                criteria = vendor.get("criteria", {})
                country_supported = (
                    country in criteria.get("supported_countries", [])
                    or "All countries" in criteria.get("supported_countries", [])
                    or not criteria.get("supported_countries")
                )
                geo_restrictions = (
                    criteria.get("geographical_restrictions", []) or []
                    if isinstance(criteria.get("geographical_restrictions"), list)
                    else []
                )
                geo_restricted = any(
                    geo_state in restriction.upper() for restriction in geo_restrictions
                )
                if country_supported and not geo_restricted:
                    filtered_vendors.append(vendor)
                    logger.info(
                        f"Vendor {vendor_name} passed country ({country}) and geo ({geo_state}) filters"
                    )
                else:
                    logger.info(
                        f"Vendor {vendor_name} filtered: country_supported={country_supported}, geo_restricted={geo_restricted}"
                    )


        # Calculate FOIR for all eligible vendors
        logger.info(f"### Step 2: FOIR Calculation")
        foir_results = {}
        for vendor, loan_preference in eligible_vendors:
            vendor_name = vendor.get("vendorName")
            co_applicant_income = co_applicant_details.get("co_applicant_income_amount", {}).get("amount", 0)
            monthly_income = co_applicant_income / 12 if co_applicant_income > 0 else 0
            foir_limit = 0.75 if monthly_income >= 100000 else 0.60
            
            foir, adjusted_loan, foir_message = calculate_foir(
                student_profile,
                vendor,
                loan_amount,
                loan_preference=loan_preference,
                foir_limit=foir_limit
            )
            foir_results[(vendor_name, loan_preference)] = {
                "foir": foir,
                "adjusted_loan": adjusted_loan,
                "message": foir_message
            }
            
            interest_rate = vendor["criteria"].get(
                "interest_rate_secured" if loan_preference == "Secured" else "interest_rate_unsecured",
                vendor["criteria"].get("interest_rate_unsecured_upto", "10%")
            )
            logger.info(f"{vendor_name}:\n"
                        f"  - Interest Rate: {interest_rate}\n"
                        f"  - Adjusted Loan: {format_amount(adjusted_loan)} INR\n"
                        f"  - FOIR: {foir:.2f}%\n"
                        f"  - FOIR Suggestion: {foir_message}")

        # Calculate scores and rank vendors
        logger.info("### Step 3: Scoring and Ranking")
        scored_vendors = []
        
        for vendor, loan_preference in eligible_vendors:
            vendor_name = vendor.get("vendorName")
            score = calculate_vendor_score(
                vendor, 
                student_profile, 
                loan_preference, 
                university_vendors, 
                no_university_vendors, 
                foir_results
            )
            
            # Only include vendors with score >= 50
            if score >= 50:
                criteria = vendor.get("criteria", {})

                foir_result = foir_results.get((vendor_name, loan_preference), {})
                
                # Determine match type based on score
                if score >= 80:
                    match_type = "Best Match"
                else:
                    match_type = "Near Match"
                
                # Get vendor details
                interest_rate = criteria.get(
                    "interest_rate_secured" if loan_preference == "Secured" else "interest_rate_unsecured",
                    criteria.get("interest_rate_unsecured_upto", "10%")
                )
                loan_tenor = criteria.get("loan_tenor_years", 15)
                processing_fee = criteria.get("processing_fee", "1%")
                moratorium_period = criteria.get("moratorium_period", "Course duration + 6 months")
                repayment_options = criteria.get("repayment_options", ["SI", "EMI"])
                
                vendor_match = {
                    "vendor_id": f"{vendor_name.replace(' ', '_').lower()}_{loan_preference.lower()}",
                    "vendor_name": vendor_name,
                    "loan_type": loan_preference,
                    "match_type": match_type,
                    "score": score,
                    "reason": f"Function-based match for {vendor_name} ({loan_preference}) with score {score}/100",
                    "adjusted_loan_amount_inr": foir_result.get("adjusted_loan", loan_amount),
                    "interest_rate": interest_rate,
                    "loan_tenor": loan_tenor,
                    "processing_fee": processing_fee,
                    "moratorium_period": moratorium_period,
                    "repayment_options": repayment_options,
                    "foir_suggestion": foir_result.get("message", "Loan amount within limits")
                }
                
                scored_vendors.append(vendor_match)
                logger.info(f"{vendor_name} ({loan_preference}):\n"
                            f"  - Score: {score}\n"
                            f"  - Match Type: {match_type}")

        # Sort by score (descending)
        scored_vendors.sort(key=lambda x: x["score"], reverse=True)

        # Generate summary
        summary_text = f"Function-based matching completed. Found {len(scored_vendors)} eligible vendors."
        if no_university_vendors:
            summary_text += " Note: University-specific vendor list not found, used all vendors."

                reasons = []
                is_eligible = True
                effective_loan_type = loan_preference

                logger.info(f"{vendor_name}:")

                # Country (already filtered)
                logger.info(f"  - Supported Country: Yes")

                # Degree
                if intended_degree and intended_degree not in criteria.get(
                    "supported_degrees", []
                ):
                    reasons.append(
                        f"Intended degree {intended_degree} not in supported_degrees"
                    )
                    is_eligible = False
                    logger.info(f"  - Supported Degree: No")
                else:
                    logger.info(f"  - Supported Degree: Yes")

                # Loan amount
                max_unsecured_inr = criteria.get("max_unsecured_loan_inr")
                max_unsecured_usd = criteria.get("max_unsecured_loan_usd")
                if max_unsecured_usd:
                    max_unsecured_inr = max_unsecured_usd * get_usd_to_inr_rate()
                max_secured_inr = criteria.get("max_secured_loan_inr")
                min_loan_eligible = loan_amount
                if (
                    co_applicant_income / 12 > 60000
                    and not co_applicant_details.get("co_applicant_existing_loan", "No")
                    == "Yes"
                ):
                    min_loan_eligible = max(min_loan_eligible, 7000000)
                if (
                    isinstance(cibil_score, str)
                    and cibil_score.isdigit()
                    and int(cibil_score) >= 700
                    and bank_balance
                ):
                    min_loan_eligible = max(min_loan_eligible, 10000000)

                # Check if Secured is viable
                secured_viable = (
                    loan_preference == "Secured"
                    and max_secured_inr
                    and loan_amount <= max_secured_inr
                )
                unsecured_viable = (
                    max_unsecured_inr and loan_amount <= max_unsecured_inr
                )

                if loan_preference == "Secured":
                    if secured_viable:
                        logger.info(f"  - Loan Amount: Meets max secured loan")
                    if (
                        collateral_existing_loan
                        and collateral_value
                        and loan_amount < collateral_value
                    ):
                        logger.info(
                            f"  - Loan Amount: Below collateral value, evaluating Unsecured"
                        )
                        effective_loan_type = "Unsecured"
                        unsecured_viable = (
                            max_unsecured_inr and loan_amount <= max_unsecured_inr
                        )
                        if not unsecured_viable:
                            reasons.append(
                                f"Loan amount {format_amount(loan_amount)} exceeds max_unsecured_loan_inr {format_amount(max_unsecured_inr)} after collateral adjustment"
                            )
                            is_eligible = False
                            logger.info(
                                f"  - Loan Amount: Exceeds max unsecured loan after adjustment"
                            )
                    elif not secured_viable:
                        reasons.append(
                            f"Loan amount {format_amount(loan_amount)} exceeds max_secured_loan_inr {format_amount(max_secured_inr)}"
                        )
                        is_eligible = False
                        logger.info(f"  - Loan Amount: Exceeds max secured loan")
                else:  # Unsecured
                    if not unsecured_viable:
                        reasons.append(
                            f"Loan amount {format_amount(loan_amount)} exceeds max_unsecured_loan_inr {format_amount(max_unsecured_inr)}"
                        )
                        is_eligible = False
                        logger.info(f"  - Loan Amount: Exceeds max unsecured loan")
                    else:
                        logger.info(f"  - Loan Amount: Meets max unsecured loan")

                # CIBIL score
                cibil_requirement = criteria.get("cibil_score_requirement", "None")
                cibil_ok = (
                    cibil_requirement == "None"
                    or "preferred" in cibil_requirement.lower()
                    or (
                        isinstance(cibil_score, str)
                        and cibil_score.isdigit()
                        and int(cibil_score) >= int(cibil_requirement.split("+")[0])
                        if cibil_requirement.replace("preferred", "")
                        .replace("+", "")
                        .isdigit()
                        else False
                    )
                )
                if not cibil_ok:
                    reasons.append(
                        f"CIBIL score {cibil_score} does not meet requirement {cibil_requirement}"
                    )
                    is_eligible = False
                    logger.info(f"  - CIBIL Score: Does not meet requirement")
                else:
                    logger.info(f"  - CIBIL Score: Meets requirement")

                # Loan preference
                loan_options = normalize_loan_options(criteria.get("loan_options", []))
                if effective_loan_type not in loan_options:
                    reasons.append(
                        f"Loan preference {effective_loan_type} not in loan_options"
                    )
                    is_eligible = False
                    logger.info(
                        f"  - Loan Preference: Does not match {effective_loan_type.lower()}"
                    )
                else:
                    logger.info(
                        f"  - Loan Preference: Matches {effective_loan_type.lower()}"
                    )

                # Co-applicant
                supported_relations = (
                    criteria.get("supported_co_applicant_relations", []) or []
                )
                if criteria.get("requires_co_applicant") and not co_applicant_available:
                    reasons.append("Co-applicant required but not available")
                    is_eligible = False
                    logger.info(f"  - Co-Applicant: Required but not available")
                elif (
                    criteria.get("requires_co_applicant")
                    and co_applicant_relation
                    and co_applicant_relation not in supported_relations
                ):
                    reasons.append(
                        f"Co-applicant relation {co_applicant_relation} not supported"
                    )
                    is_eligible = False
                    logger.info(f"  - Co-Applicant: Relation not supported")
                else:
                    logger.info(
                        f"  - Co-Applicant: {'Available' if co_applicant_available else 'Not required'}"
                    )

                # Collateral
                requires_collateral = criteria.get("requires_collateral")
                if requires_collateral is None:
                    requires_collateral = (
                        True if effective_loan_type == "Secured" else False
                    )
                if requires_collateral and not collateral_available:
                    reasons.append("Collateral required but not available")
                    is_eligible = False
                    logger.info(f"  - Collateral: Required but not available")
                else:
                    logger.info(
                        f"  - Collateral: {'Not required' if not requires_collateral else 'Available'}"
                    )

                # Own house
                if (
                    criteria.get("own_house_required")
                    and vendor_name
                    not in [
                        "HDFC Credila",
                        "Avanse",
                        "Auxilo",
                        "Avanse Global",
                        "Prodigy",
                        "Mpower",
                    ]
                    and not own_house
                ):
                    reasons.append("Own house required but not provided")
                    is_eligible = False
                    logger.info(f"  - Own House: Required but not provided")
                else:
                    logger.info(
                        f"  - Own House: {'Not required' if vendor_name in ['HDFC Credila', 'Avanse', 'Auxilo', 'Avanse Global', 'Prodigy', 'Mpower'] else 'Provided or not required'}"
                    )

                # Admission status
                if vendor_name == "HDFC Credila":
                    admission_ok = True
                    logger.info(f"  - Admission Status: Any status allowed")
                elif (
                    vendor_name in ["HDFC Credila", "IDFC Bank", "Yes Bank"]
                    and admission_status == "Conditional letter received"
                ):
                    test_ok = (
                        english_test_score is None
                        or (
                            english_test_type == "IELTS"
                            and english_test_score
                            >= criteria.get("min_ielts_score", float("inf"))
                            or english_test_type == "TOEFL"
                            and english_test_score
                            >= criteria.get("min_toefl_score", float("inf"))
                        )
                    ) and (
                        standardized_test_score is None
                        or standardized_test_score
                        >= criteria.get("min_gmat_score", float("inf"))
                    )
                    if not test_ok:
                        reasons.append(
                            f"Test scores insufficient: {english_test_type} {english_test_score} < {criteria.get('min_ielts_score', criteria.get('min_toefl_score'))}, GMAT {standardized_test_score} < {criteria.get('min_gmat_score')}"
                        )
                        is_eligible = False
                    admission_ok = test_ok
                    logger.info(
                        f"  - Admission Status: {'Conditional letter received' if test_ok else 'Test scores insufficient'}"
                    )
                else:
                    requires_admission = criteria.get("requires_admission")
                    admission_ok = True
                    if isinstance(requires_admission, bool):
                        admission_ok = not requires_admission or admission_status in [
                            "Admission letter received",
                            "Conditional letter received",
                        ]
                    elif isinstance(requires_admission, list):
                        admission_ok = any(
                            entry.get("Admission Letter")
                            or entry.get("Conditional Admission")
                            for entry in requires_admission
                        ) and admission_status in [
                            "Admission letter received",
                            "Conditional letter received",
                        ]
                    elif requires_admission is not None:
                        logger.warning(
                            f"Invalid requires_admission format for vendor {vendor_name}: {requires_admission}"
                        )
                        admission_ok = False
                    if not admission_ok:
                        reasons.append(
                            f"Admission status {admission_status} does not meet requirement"
                        )
                        is_eligible = False
                    logger.info(
                        f"  - Admission Status: {'Yes' if admission_ok else 'No'}"
                    )

                # Log secondary criteria
                supported_courses = [
                    c.replace("-", "") for c in criteria.get("supported_courses", [])
                ]
                course_match = course_type.lower() in [
                    sc.lower() for sc in supported_courses
                ]
                logger.info(f"  - Supported Courses: {'Yes' if course_match else 'No'}")

                academic_ok = not criteria.get(
                    "min_academic_score_percentage"
                ) or academic_score >= criteria.get("min_academic_score_percentage")
                logger.info(
                    f"  - Academic Score: {'Meets requirement' if academic_ok else 'Below minimum'}"
                )

                age_ok = not criteria.get("max_student_age") or (
                    age and age <= criteria.get("max_student_age")
                )
                logger.info(
                    f"  - Age: {'Within limit' if age_ok else 'Exceeds maximum'}"
                )

                backlogs_ok = criteria.get(
                    "max_educational_backlogs"
                ) is None or backlogs <= criteria.get("max_educational_backlogs")
                logger.info(
                    f"  - Backlogs: {'Within limit' if backlogs_ok else 'Exceeds maximum'}"
                )

                if is_eligible:
                    eligible_vendors.append((vendor, effective_loan_type))
                    logger.info(f"  - Match: Yes")
                else:
                    logger.info(f"  - Match: No ({', '.join(reasons)})")

            # FOIR calculation
            logger.info(f"### Step 2: FOIR Calculation ({loan_preference})")
            for vendor, pref in eligible_vendors:
                vendor_name = vendor.get("vendorName")
                monthly_income = co_applicant_income / 12
                foir_limit = 0.75 if monthly_income >= 100000 else 0.60
                foir, adjusted_loan, foir_message = calculate_foir(
                    student_profile,
                    vendor,
                    loan_amount,
                    loan_preference=pref,
                    foir_limit=foir_limit,
                )
                foir_results[(vendor_name, pref)] = {
                    "foir": foir,
                    "adjusted_loan": adjusted_loan,
                    "message": foir_message,
                }
                interest_rate = vendor["criteria"].get(
                    (
                        "interest_rate_secured"
                        if pref == "Secured"
                        else "interest_rate_unsecured"
                    ),
                    vendor["criteria"].get("interest_rate_unsecured_upto", "10%"),
                )
                logger.info(
                    f"{vendor_name}:\n"
                    f"  - Interest Rate: {interest_rate}\n"
                    f"  - Proposed EMI: {format_amount(adjusted_loan)} INR\n"
                    f"  - FOIR: {foir:.2f}%\n"
                    f"  - FOIR Suggestion: {foir_message}"
                )

            all_eligible_vendors.extend(eligible_vendors)

        logger.info(
            f"Eligible vendors for LLM: {len(all_eligible_vendors)} - {[(v['vendorName'], lp) for v, lp in all_eligible_vendors]}"
        )

        # Prepare LLM input
        profile_summary = {
            "Dest Country": country,
            "Dest Countries": student_profile.get("education_details", {}).get(
                "study_destination_country", []
            ),
            "Intended Degree": intended_degree,
            "University": university,
            "Universities": student_profile.get("education_details", {}).get(
                "university_name", []
            ),
            "Course Category": course_type,
            "Loan Amount INR": loan_amount,
            "Collateral Available": collateral_available,
            "Collateral Type": collateral_type,
            "Collateral Value INR": collateral_value,
            "Collateral Location State": collateral_location_state,
            "Collateral Existing Loan": not collateral_existing_loan,
            "Co-Applicant Available": co_applicant_available,
            "Co-Applicant Relation": co_applicant_relation,
            "Co-Applicant Occupation": co_applicant_occupation,
            "Co-Applicant Income INR (Annual)": co_applicant_income,
            "Co-Applicant Existing EMI INR": (
                co_applicant_details.get(
                    "co_applicant_existing_loan_emi_amount", {}
                ).get("amount", 0)
                if isinstance(
                    co_applicant_details.get("co_applicant_existing_loan_emi_amount"),
                    dict,
                )
                else 0
            ),
            "Co-Applicant EMI Default": (
                "Yes"
                if co_applicant_details.get("co_applicant_emi_default") == "Yes"
                else "No"
            ),
            "Academic Score %": academic_score,
            "Age": age,
            "Backlogs": backlogs,
            "Admission Status": admission_status,
            "English Test Type": english_test_type,
            "English Test Score": english_test_score,
            "Standardized Test Type": standardized_test_type,
            "Standardized Test Score": standardized_test_score,
            "CIBIL Score": cibil_score,
            "Course Duration Years": course_duration_years,
            "Own House": own_house,
            "Bank Balance Available": bank_balance,
            "Geo State": geo_state,
        }
        logger.info(
            f"Profile summary for matching: {json.dumps(profile_summary, default=str, ensure_ascii=False)}"
        )

        vendor_details_list = []
        seen_vendors = set()
        for vendor, loan_preference in all_eligible_vendors:
            vendor_name = vendor.get("vendorName")
            key = (vendor_name, loan_preference)
            if key not in seen_vendors:
                seen_vendors.add(key)
                vendor_details_list.append(
                    {
                        "id": f"{vendor_name.replace(' ', '_').lower()}_{loan_preference.lower()}",
                        "name": vendor_name,
                        "loan_type": loan_preference,
                        "criteria": {
                            k: v
                            for k, v in vendor.get("criteria", {}).items()
                            if v is not None
                        },
                    }
                )
        vendors_str = json.dumps(vendor_details_list, ensure_ascii=False, indent=2)
        logger.info(f"Prepared vendor data for LLM: {len(vendor_details_list)} vendors")

        foir_results_dict = {
            f"{k[0]}_{k[1].lower()}": v for k, v in foir_results.items()
        }
        foir_results_str = json.dumps(foir_results_dict, ensure_ascii=False, indent=2)

        # LLM prompt with explicit loan_type field
        prompt = f"""Analyze the student profile against vendors, prioritizing country, loan type, and other primary criteria, with education details as secondary.

Profile: {json.dumps(profile_summary, ensure_ascii=False, indent=2)}
Vendors: {vendors_str}
FOIR Results: {foir_results_str}

Task:
1. **Primary Matching** (Mandatory for Inclusion):
   - Country: Dest Country must be in supported_countries or supported_countries is empty or includes "All countries".
   - Geo Restrictions: Geo State must not be in geographical_restrictions (empty or False passes).
   - Loan Type: For Secured, loan_options must include "Secured" or "Secured & Unsecured"; for Unsecured, include "Unsecured" or "Secured & Unsecured". If Collateral Existing Loan is False and Loan Amount INR < Collateral Value INR, evaluate both Secured (if within max_secured_loan_inr) and Unsecured (if in loan_options).
   - Loan Amount: For Unsecured, Loan Amount INR ≤ max_unsecured_loan_inr (convert max_unsecured_loan_usd to INR using 83.0 rate). For Secured, Loan Amount INR ≤ max_secured_loan_inr. Minimums: INR 7000000 if Co-Applicant Income INR (Annual)/12 > 60000 and no existing EMI; INR 10000000 if CIBIL Score ≥ 700 and Bank Balance Available is True.
   - Admission Status: If requires_admission is True or a list with "Admission Letter"/"Conditional Admission", Admission Status must be "Admission letter received" or "Conditional letter received". For vendors ["HDFC Credila", "IDFC Bank", "Yes Bank"] with "Conditional letter received", English Test Score ≥ min_ielts_score (for IELTS) or min_toefl_score (for TOEFL) and Standardized Test Score ≥ min_gmat_score (skip if scores missing). HDFC Credila allows any Admission Status (including null). If requires_admission is False, skip.
   - Co-Applicant: If requires_co_applicant is True, Co-Applicant Available must be True and Co-Applicant Relation in supported_co_applicant_relations (empty passes).
   - Collateral: For Secured, if requires_collateral is True or null, Collateral Available must be True (do not check Collateral Type).
   - CIBIL Score: If cibil_score_requirement is "None" or includes "preferred", pass. If numeric, CIBIL Score ≥ requirement.
   - Own House: If own_house_required is True and vendor not in ["HDFC Credila", "Avanse Global", "Prodigy", "Mpower"], Own House must be True.

2. **Scoring** (100 points):
   - University Vendor List: +20 if vendor in university_vendors or in ["HDFC Credila", "Auxilo", "Avanse", "Tata Capital", "InCred"].
   - Loan Amount after FOIR: Use adjusted_loan_amount_inr from FOIR Results. +15 if equals Loan Amount INR, +7 if within 10%, +0 if 0 or exceeds limits.
   - Supported Country: +10 if Dest Country in supported_countries.
   - Supported Course Type: +10 if Course Category in supported_courses (case-insensitive, ignore hyphens).
   - Collateral: +8 if Collateral Available and Loan Type is Secured.
   - Loan Type: +7 if Loan Type and Collateral Available align with loan_options.
   - Admission Status: +5 if requires_admission is True (or list) and Admission Status is "Admission letter received" or "Conditional letter received". HDFC Credila gets +5 for any status.
   - Co-Applicant Salaried: +3 if Co-Applicant Available, requires_co_applicant is True, and Co-Applicant Occupation is "Salaried".
   - FOIR Score: +2 if FOIR from FOIR Results is within limit.
   - Education Details: +5 if Academic Score % (or marks_12th.value if 0) ≥ min_academic_score_percentage. +3 if English Test Score ≥ min_ielts_score (for IELTS) or min_toefl_score (for TOEFL) (or not required). +2 if Standardized Test Score ≥ min_gmat_score (or not required).
   - Backlogs: +5 if Backlogs ≤ max_educational_backlogs (or null).
   - Age and Others: +2 if Age ≤ max_student_age (or null), +2 if margin_money_percentage is 0 or met, +1 if CIBIL Score meets requirement (always +1 for "preferred").

3. **FOIR Calculation** (Use Provided FOIR Results):
   - FOIR Limit: 75% if Co-Applicant Income INR (Annual)/12 ≥ 100000, else 60% (same for all vendors).
   - Use adjusted_loan_amount_inr, foir, and foir_suggestion from FOIR Results.
   - Ensure minimum loan: INR 7000000 if Co-Applicant Income INR/12 > 60000 and no existing EMI; INR 10000000 if CIBIL Score ≥ 700 and Bank Balance Available is True.

4. **Output**:
   - Return JSON: {{"matches": [], "summary_text": "", "fallback": false}}.
   - Include all vendors from input with score ≥ 50 (Best Match ≥ 80, Near Match 50–79).
   - Structure: {{"vendor_id": "<id>-<loan_type>", "vendor_name": "<name>", "loan_type": "<Secured or Unsecured>", "match_type": "...", "score": 0–100, "reason": "...", "adjusted_loan_amount_inr": FLOAT, "interest_rate": "X%", "loan_tenor": INT, "processing_fee": "X%", "moratorium_period": "...", "repayment_options": [], "foir_suggestion": "..."}}.
   - Reason: Detail primary matches and secondary points/failures.
   - Fallback: True if no university vendors found in MongoDB.
   - Ensure vendors passing strict matching score at least 50.
"""
        logger.info("Sending prompt to OpenAI GPT-4 API")
        max_retries = 2
        for attempt in range(max_retries):
            try:
                chat_response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "Loan matching assistant."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=14000,
                    response_format={"type": "json_object"},
                )
                raw_content = chat_response.choices[0].message.content.strip()
                json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
                if not json_match:
                    logger.error("No JSON found in GPT-4 response")
                    raise ValueError("No valid JSON in GPT-4 response")
                raw_content = json_match.group(0)
                logger.info(f"Raw GPT-4 response: {raw_content[:500]}...")

                try:
                    parsed_json = json.loads(raw_content)
                    if (
                        not isinstance(parsed_json, dict)
                        or "matches" not in parsed_json
                        or "summary_text" not in parsed_json
                    ):
                        logger.error(
                            "Invalid GPT-4 response structure: missing matches or summary_text"
                        )
                        raise ValueError("Invalid GPT-4 response structure")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON response from GPT-4: {str(e)}")
                    raise ValueError(f"Invalid JSON response from GPT-4: {str(e)}")

                logger.info(f"Parsed GPT-4 response: {parsed_json.get('summary_text')}")
                parsed_json["fallback"] = no_university_vendors

                # Log ranking
                logger.info("### Step 3: Weightage-Based Ranking")
                for match in parsed_json.get("matches", []):
                    logger.info(
                        f"{match['vendor_name']} ({match.get('loan_type', 'Unknown')}):\n"
                        f"  - Score: {match['score']}\n"
                        f"  - Reason: {match['reason']}"
                    )

                # Filter matches
                matches = [
                    match
                    for match in parsed_json.get("matches", [])
                    if match["score"] >= 50
                ]
                for match in parsed_json.get("matches", []):
                    log_level = logger.info if match["score"] >= 50 else logger.debug
                    log_level(
                        f"Vendor match: {match['vendor_name']} - {match['match_type']} ({match.get('loan_type', 'Unknown')}) (Score: {match['score']}, Reason: {match['reason']}, FOIR: {match['foir_suggestion']})"
                    )

                # Final output
                logger.info("### Final Output")
                final_output = {
                    "matches": matches,
                    "summary_text": parsed_json.get("summary_text", "Matching done"),
                    "fallback": no_university_vendors,
                }
                logger.info(
                    f"Final response JSON: {json.dumps(final_output, indent=2, ensure_ascii=False)}"
                )
                logger.info(
                    f"Final response: {len(matches)} matches, fallback={no_university_vendors}"
                )

                return matches, parsed_json.get("summary_text", "Matching done")
            except Exception as e:
                logger.error(
                    f"Attempt {attempt + 1}/{max_retries} failed: Error processing GPT-4 response: {str(e)}"
                )
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                logger.warning("Falling back to manual response")
                manual_matches = [
                    {
                        "vendor_id": f"{v.get('vendorName').replace(' ', '_').lower()}_{lp.lower()}",
                        "vendor_name": v.get("vendorName"),
                        "loan_type": lp,
                        "match_type": "Near Match",
                        "score": 50,
                        "reason": f"Manual match for {v.get('vendorName')} ({lp}) due to API failure.",
                        "adjusted_loan_amount_inr": foir_results.get(
                            (v.get("vendorName"), lp), {}
                        ).get("adjusted_loan", loan_amount),
                        "interest_rate": v.get("criteria", {}).get(
                            (
                                "interest_rate_secured"
                                if lp == "Secured"
                                else "interest_rate_unsecured"
                            ),
                            "12%",
                        ),
                        "loan_tenor": v.get("criteria", {}).get("loan_tenor_years", 15),
                        "processing_fee": v.get("criteria", {}).get(
                            "processing_fee", "1%"
                        ),
                        "moratorium_period": v.get("criteria", {}).get(
                            "moratorium_period", "Course duration + 6 months"
                        ),
                        "repayment_options": v.get("criteria", {}).get(
                            "repayment_options", ["SI", "EMI"]
                        ),
                        "foir_suggestion": foir_results.get(
                            (v.get("vendorName"), lp), {}
                        ).get("message", "Loan adjusted based on profile"),
                    }
                    for v, lp in all_eligible_vendors
                ]
                logger.info("### Step 3: Weightage-Based Ranking")
                for match in manual_matches:
                    logger.info(
                        f"{match['vendor_name']} ({match['loan_type']}):\n"
                        f"  - Score: {match['score']}\n"
                        f"  - Reason: {match['reason']}"
                    )
                logger.info("### Final Output")
                final_output = {
                    "matches": manual_matches,
                    "summary_text": f"Manual matching due to API error: {str(e)}",
                    "fallback": no_university_vendors,
                }
                logger.info(
                    f"Final response JSON: {json.dumps(final_output, indent=2, ensure_ascii=False)}"
                )
                logger.info(
                    f"Final response: {len(manual_matches)} matches, fallback={no_university_vendors}"
                )
                return manual_matches, f"Manual matching due to API error: {str(e)}"
    except Exception as e:
        logger.error(f"Error matching vendors: {str(e)}")
        return [], f"Error matching vendors: {str(e)}"


        logger.info("### Final Output")
        logger.info(f"Final response: {len(scored_vendors)} matches, fallback={no_university_vendors}")
        
        return scored_vendors, summary_text

    except Exception as e:
        logger.error(f"Error in function-based vendor matching: {str(e)}")
        return [], f"Error in vendor matching: {str(e)}"

def generate_function_based_document_list(student_profile: Dict) -> str:
    """Generate a tailored document list using function-based logic."""
    student_id = student_profile.get("student_id", "?")

    logger.info(f"Generating function-based document list for student {student_id}")
    
    co_applicant_details = student_profile.get("co_applicant_details", {})
    education_details = student_profile.get("education_details", {})
    loan_details = student_profile.get("loan_details", {})
    
    if loan_details.get("co_applicant_available") == "Yes" and not co_applicant_details:
        logger.warning("Co-applicant details missing despite co_applicant_available: Yes")
        co_applicant_details = {
            "co_applicant_occupation": "Salaried",
            "co_applicant_relation": loan_details.get("co_applicant_relation", "Unknown")
        }

    # Base document structure
    document_sections = OrderedDict()
    
    # Student Documents (always included)
    student_docs = [
        "Photograph",
        "Aadhaar Card", 
        "PAN Card",
        "Passport",
        "Offer Letter",
        "10th/12th Marksheet and Passing Certificate"
    ]
    
    # Add degree documents if applicable
    highest_education = education_details.get("highest_education_level", "")
    if highest_education and highest_education not in ["High School", "12th Grade"]:
        student_docs.append("Degree Marksheet and Certificate")
    
    # Add test scorecards if applicable
    english_test = education_details.get("english_test", {})
    standardized_test = education_details.get("standardized_test", {})
    if (english_test.get("type") and english_test.get("type") != "None") or (standardized_test.get("type") and standardized_test.get("type") != "None"):
        student_docs.append("Scorecard (IELTS, TOEFL, GRE, etc., if applicable)")
    
    student_docs.extend([
        "Student Email ID and Phone Number",
        "Bank Statements (Last 6 Months)"
    ])
    
    document_sections["Student Documents (PDF)"] = student_docs
    
    # Co-applicant documents based on occupation
    if loan_details.get("co_applicant_available") == "Yes":
        co_applicant_occupation = co_applicant_details.get("co_applicant_occupation", "Salaried")
        
        base_co_applicant_docs = [
            "Photograph",
            "PAN Card", 
            "Aadhaar Card"
        ]
        
        if co_applicant_occupation == "Salaried":
            co_applicant_docs = base_co_applicant_docs + [

    logger.info(f"Generating document list for student {student_id}")

    co_applicant_details = student_profile.get("co_applicant_details", {})
    if (
        student_profile.get("loan_details", {}).get("co_applicant_available") == "Yes"
        and not co_applicant_details
    ):
        logger.warning(
            "Co-applicant details missing despite co_applicant_available: Yes"
        )
        co_applicant_details = {
            "co_applicant_occupation": "Salaried",
            "co_applicant_relation": student_profile.get("loan_details", {}).get(
                "co_applicant_relation", "Unknown"
            ),
        }

    if not OPENAI_API_KEY:
        logger.warning("OpenAI API key missing, using mock response")
        return """Required Documents for Education Loan - Unsecured
Student Documents (PDF):
1. Photograph
2. Aadhaar Card
3. PAN Card
4. Passport
5. Offer Letter
6. 10th/12th Marksheet and Passing Certificate
7. Degree Marksheet and Certificate (if applicable)
8. Student Email ID and Phone Number
9. Bank Statements (Last 6 Months)
Co-Applicant Documents (Salaried, PDF):
1. Photograph
2. PAN Card
3. Aadhaar Card
4. Last 3 Months Salary Slips
5. Last 6 Months Bank Statement
6. Last 2 Years Form 16
7. Utility Bill (e.g., Electricity Bill)
8. Rent Agreement (if applicable)
9. Co-Applicant Phone Number and Email ID"""

    profile_summary = {
        "Loan Type": (
            "Secured"
            if student_profile.get("loan_details", {}).get("collateral_available")
            == "Yes"
            else "Student Fees"
        ),
        "Collateral Type": student_profile.get("loan_details", {}).get(
            "collateral_type", ""
        ),
        "Co-Applicant Available": student_profile.get("loan_details", {}).get(
            "co_applicant_available"
        )
        == "Yes",
        "Co-Applicant Occupation": co_applicant_details.get(
            "co_applicant_occupation", ""
        ),
        "Highest Education": student_profile.get("education_details", {}).get(
            "highest_education_level", ""
        ),
        "Admission Status": student_profile.get("education_details", {}).get(
            "admission_status",
            student_profile.get("education_details", {}).get(
                "university_admission_status", ""
            ),
        ),
        "English Test Type": student_profile.get("education_details", {})
        .get("english_test", {})
        .get("type", ""),
        "Standardized Test Type": student_profile.get("education_details", {})
        .get("standardized_test", {})
        .get("type", ""),
    }
    profile_str = json.dumps(profile_summary, ensure_ascii=False, indent=2)
    logger.info(f"Profile summary for document generation: {profile_str}")

    base_docs = {
        "Student Fees": {
            "Student Documents (PDF)": [
                "Photograph",
                "Aadhaar Card",
                "PAN Card",
                "Passport",
                "Offer Letter",
                "10th/12th Marksheet and Passing Certificate",
                "Degree Marksheet and Certificate (if applicable)",
                "Scorecard (IELTS, TOEFL, GRE, etc., if applicable)",
                "Student Email ID and Phone Number",
                "Bank Statements (Last 6 Months)",
            ],
            "Co-Applicant Documents (Salaried, PDF)": [
                "Photograph",
                "PAN Card",
                "Aadhaar Card",

                "Last 3 Months Salary Slips",
                "Last 6 Months Bank Statement",
                "Last 2 Years Form 16",
                "Utility Bill (e.g., Electricity Bill)",
                "Rent Agreement (if applicable)",

                "Co-Applicant Phone Number and Email ID"
            ]
            document_sections["Co-Applicant Documents (Salaried, PDF)"] = co_applicant_docs
            
        elif co_applicant_occupation == "Self-Employed":
            co_applicant_docs = base_co_applicant_docs + [

                "Co-Applicant Phone Number and Email ID",
            ],
            "Co-Applicant Documents (Self-Employed, PDF)": [
                "Photograph",
                "PAN Card",
                "Aadhaar Card",

                "GST 3B Last 1 Year and GST Certificate (Merged PDF)",
                "ITR of Last 2 Years with Computation Page",
                "Current Account Statement (Last 6 Months)",
                "Savings Account Statement (Last 6 Months)",
                "Audit Report of Last 2 Years",
                "Utility Bill (e.g., Electricity Bill)",

                "Co-Applicant Phone Number and Email ID"
            ]
            document_sections["Co-Applicant Documents (Self-Employed, PDF)"] = co_applicant_docs
            
        elif co_applicant_occupation == "Farmer":
            co_applicant_docs = base_co_applicant_docs + [
                "Land Ownership Documents",
                "Last 6 Months Bank Statement",
                "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID"
            ]
            document_sections["Co-Applicant Documents (Farmer, PDF)"] = co_applicant_docs
            
        else:  # Unemployed or Other
            co_applicant_docs = base_co_applicant_docs + [
                "Last 6 Months Bank Statement (if applicable)",
                "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID"
            ]
            section_name = f"Co-Applicant Documents ({co_applicant_occupation or 'Other'}, PDF)"
            document_sections[section_name] = co_applicant_docs
    
    # Collateral documents for secured loans
    if loan_details.get("collateral_available") == "Yes":
        collateral_type = loan_details.get("collateral_type", "")
        
        if collateral_type in ["Residential", "Commercial"]:
            property_docs = [

                "Co-Applicant Phone Number and Email ID",
            ],
            "Co-Applicant Documents (Farmer, PDF)": [
                "Photograph",
                "PAN Card",
                "Aadhaar Card",
                "Land Ownership Documents",
                "Last 6 Months Bank Statement",
                "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID",
            ],
            "Co-Applicant Documents (Unemployed, PDF)": [
                "Photograph",
                "PAN Card",
                "Aadhaar Card",
                "Last 6 Months Bank Statement (if applicable)",
                "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID",
            ],
            "Co-Applicant Documents (Other, PDF)": [
                "Photograph",
                "PAN Card",
                "Aadhaar Card",
                "Last 6 Months Bank Statement (if applicable)",
                "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID",
            ],
        },
        "Secured": {
            "Property Documents (Residential or Commercial)": [

                "Complete Registered Agreement",
                "Index 2",
                "Title Deed",
                "Sale Deed",
                "Sanctioned Plan (Blueprint)",

                "Non-Agricultural Order"
            ]
            document_sections[f"Property Documents ({collateral_type})"] = property_docs
            document_sections["Property Owners"] = ["PAN Card", "Aadhaar Card"]
        elif collateral_type == "FD":
            document_sections["Fixed Deposit Documents"] = [
                "Fixed Deposit Receipt",
                "Bank Statement showing FD",
                "FD Holder's PAN Card",
                "FD Holder's Aadhaar Card"
            ]
    
    # Format as readable text
    formatted_docs = []
    for section, docs in document_sections.items():
        formatted_docs.append(f"{section}:")
        for i, doc in enumerate(docs, 1):
            formatted_docs.append(f"{i}. {doc}")
        formatted_docs.append("")
    
    result = "\n".join(formatted_docs).strip()
    logger.info(f"Generated function-based document list with {len(document_sections)} sections")
    
    return result




# Update the main function to use function-based approach
def get_vendor_matches(student_profile: Dict, vendors: Optional[List[Dict]] = None, use_llm: bool = False) -> Tuple[List[Dict], Optional[str]]:
    """
    Main function to get vendor matches. 
    Always uses function-based approach since GPT-4 dependency is removed.
    """
    return get_function_based_vendor_matches(student_profile, vendors)

def generate_document_list(student_profile: Dict, use_llm: bool = False) -> str:
    """
    Main function to generate document list.
    Always uses function-based approach since GPT-4 dependency is removed.
    """
    return generate_function_based_document_list(student_profile)

def generate_profile_suggestions(profile_data: Dict) -> List[Dict]:
    """Generate AI-powered suggestions for improving a student's loan profile."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_api_key:
        logger.error("OpenAI API key not found")
        return []

    client = OpenAI(api_key=openai_api_key)
    
    # Optimized prompt for GPT-3.5-turbo: Simplified, strict JSON instruction
    prompt_template = """
You are an expert education loan advisor. Analyze the student's profile and provide 5-7 actionable suggestions to improve loan eligibility, targeting more vendor matches, better rates, higher amounts, and approval chances.

# PROFILE
{{student_profile_json}}

# CRITERIA
- Academic: marks_10th.value, marks_12th.value (min 60%)
- Tests: IELTS (min 6), TOEFL (min 80), PTE (min 51)
- Study: study_destination_country, university_name
- Financial: co_applicant_income_amount.amount (min ₹20,000/month), collateral_available
- CIBIL: cibil_score (min 700 for higher limits)
- Course: intended_degree (Master's preferred), course_type
- FOIR: 75% (income ≥ ₹100,000/month) or 50%; Master's with PSI uses ₹5,000 EMI during moratorium if CIBIL ≥ 700

# FORMAT
Return a JSON array of 5-7 objects:
{
  "title": "<≤10 words>",
  "description": "<2-3 sentences, ≤50 words>",
  "priority": "high|medium|low",
  "timeframe": "<e.g., 1-2 weeks>",
  "impact": "<specific benefit, e.g., Increases eligibility by 20%>"
}
Sort by priority (high first). Output MUST be valid JSON, no extra text or markdown.

# GUIDELINES
- Verify fields (e.g., study_destination_country, course_type) to avoid irrelevant suggestions.
- Prioritize low income, no collateral, low scores.
- Suggest collateral, higher IELTS (<7), stronger co-applicant.
- For Master's with PSI and CIBIL ≥ 700, highlight full loan potential.
- Respond with plain JSON only. No markdown, no ```json tags.
- Ensure realistic, high-impact fixes.
    """
    
    # Replace placeholder with profile data
    prompt = prompt_template.replace("{{student_profile_json}}", json.dumps(profile_data, indent=2))
    
    # Retry logic for robust parsing
             "Non-Agricultural Order",
            ],
            "Property Owners": ["PAN Card", "Aadhaar Card"],
        },
    }
    base_docs_str = json.dumps(base_docs, ensure_ascii=False, indent=2)
    logger.info("Base document requirements prepared")

    prompt = f"""Generate a JSON object containing a deduplicated document list for a student applying for an education loan based on their profile.

Profile: {profile_str}
Base Document Requirements: {base_docs_str}

Task:
1. **Document Selection**:
   - Always include 'Student Documents (PDF)'.
   - Exclude 'Degree Marksheet and Certificate' if Highest Education is 'High School' or below.
   - Include test scorecards only if English Test Type or Standardized Test Type is not empty or 'None'.
   - Include co-applicant documents based on Co-Applicant Occupation (Salaried, Self-Employed, Farmer, Unemployed, Other).
   - For Secured loans, include additional documents only for the specified Collateral Type (e.g., Residential, Commercial); exclude Funds (FD) unless Collateral Type is explicitly FD.
   - If Co-Applicant Available is false, exclude co-applicant documents.
   - If Co-Applicant Occupation is empty or 'Unemployed', exclude income-related documents (e.g., Salary Slips, ITR).
2. **Deduplication**:
   - Ensure no duplicate documents are listed across sections (e.g., 'PAN Card' appears only once per section).
   - Combine similar documents into a single entry (e.g., 'Bank Statements' should not be listed multiple times).
3. **Output Format**:
   - Return a JSON object with sections as keys (e.g., 'Student Documents (PDF)', 'Co-Applicant Documents (Salaried, PDF)') and lists of unique documents as values.
   - Do NOT include any duplicate entries within or across sections.
   - Respond ONLY with the JSON object, without markdown, code blocks, or explanatory text.
"""
    logger.info("Sending document generation prompt to OpenAI GPT-4 API")

    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[

                    {"role": "system", "content": "You are an expert education loan advisor. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                
            )
            
            content = response.choices[0].message.content.strip()
            logger.debug("OpenAI response: %s", content[:500])
            
            # Parse JSON response
            try:
                suggestions = json.loads(content)
                if isinstance(suggestions, list) and 5 <= len(suggestions) <= 7:
                    # Validate suggestion structure
                    valid = all(
                        isinstance(s, dict) and all(k in s for k in ["title", "description", "priority", "timeframe", "impact"])
                        and s["priority"] in ["high", "medium", "low"]
                        and len(s["title"].split()) <= 10
                        and len(s["description"].split()) <= 50
                        for s in suggestions
                    )
                    if valid:
                        return suggestions
            except json.JSONDecodeError:
                # Try extracting from markdown
                json_match = re.search(r"```(?:json)?\n([\s\S]*?)\n```", content, re.DOTALL)
                if json_match:
                    try:
                        suggestions = json.loads(json_match.group(1))
                        if isinstance(suggestions, list) and 5 <= len(suggestions) <= 7:
                            valid = all(
                                isinstance(s, dict) and all(k in s for k in ["title", "description", "priority", "timeframe", "impact"])
                                and s["priority"] in ["high", "medium", "low"]
                                for s in suggestions
                            )
                            if valid:
                                return suggestions
                    except json.JSONDecodeError:
                        pass
            
            logger.warning("Failed to parse OpenAI response on attempt %d", attempt + 1)
            if attempt < max_retries - 1:
                time.sleep(1)  # Brief delay before retry
                continue
            return []
        except Exception as e:
            logger.error("Error calling OpenAI API on attempt %d: %s", attempt + 1, str(e))

                    {"role": "system", "content": "Document list generator."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            raw_content = chat_response.choices[0].message.content.strip()
            logger.info(
                f"Raw GPT-4 response for document list: {raw_content[:500]}..."
            )  # Truncate for brevity
            if not raw_content.strip():
                logger.error("GPT-4 API returned empty response for document list")
                raise ValueError("Empty response from GPT-4 API")

            parsed_json = json.loads(raw_content)

            # Deduplicate documents programmatically
            deduplicated_docs = OrderedDict()
            seen_documents = set()
            for section, docs in parsed_json.items():
                unique_docs = []
                for doc in docs:
                    doc_lower = doc.lower()
                    if doc_lower not in seen_documents:
                        unique_docs.append(doc)
                        seen_documents.add(doc_lower)
                deduplicated_docs[section] = unique_docs
            logger.info(
                f"Deduplicated document list: {json.dumps(deduplicated_docs, ensure_ascii=False, indent=2)}"
            )

            # Format as readable text
            formatted_docs = []
            for section, docs in deduplicated_docs.items():
                formatted_docs.append(f"{section}:")
                for i, doc in enumerate(docs, 1):
                    formatted_docs.append(f"{i}. {doc}")
                formatted_docs.append("")
            result = "\n".join(formatted_docs).strip()
            logger.info(f"Formatted document list: {result}")
            return result
        except Exception as e:
            logger.error(
                f"Attempt {attempt + 1}/{max_retries} failed: GPT-4 API call failed: {str(e)}"
            )

            if attempt < max_retries - 1:
                time.sleep(1)
                continue

            return []
    
    logger.error("Failed to generate valid suggestions after %d attempts", max_retries)
    return []

            logger.warning("Falling back to manual document list due to API failure")
            return """Required Documents for Education Loan - Unsecured
Student Documents (PDF):
1. Photograph
2. Aadhaar Card
3. PAN Card
4. Passport
5. Offer Letter
6. 10th/12th Marksheet and Passing Certificate
7. Degree Marksheet and Certificate (if applicable)
8. Student Email ID and Phone Number
9. Bank Statements (Last 6 Months)
Co-Applicant Documents (Salaried, PDF):
1. Photograph
2. PAN Card
3. Aadhaar Card
4. Last 3 Months Salary Slips
5. Last 6 Months Bank Statement
6. Last 2 Years Form 16
7. Utility Bill (e.g., Electricity Bill)
8. Rent Agreement (if applicable)
9. Co-Applicant Phone Number and Email ID"""

