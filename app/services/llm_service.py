import os
import json
import re
import logging
import requests
from typing import Optional, Tuple, List, Dict
from datetime import datetime
from openai import OpenAI
import time
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
from collections import OrderedDict
from functools import lru_cache

# Load environment variables
load_dotenv()

# Configure logging with UTF-8 support
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.info("OpenAI API configuration loaded")
else:
    logger.warning("OpenAI API key missing, will use mock response")

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
        response = requests.get(EXCHANGE_RATE_URL, params={"api_key": EXCHANGE_RATE_API_KEY}, timeout=5)
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
        response = requests.get(CURRENCYLAYER_URL, params={"access_key": CURRENCYLAYER_API_KEY, "currencies": "INR"}, timeout=5)
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
    mongo_client.admin.command('ping')
    db = mongo_client.get_database("FA_bots")
    universities_collection = db["universities"]
    logger.info("Successfully connected to MongoDB")
except ConnectionFailure as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    universities_collection = None

# Placeholder for VENDORS list (to be added manually)
VENDORS = [
    {
        "vendorName": "axisbank",
        "vendorType": "Private",
        "active": True,
        "criteria": {
            "loan_options": ["Secured & Unsecured"],
            "max_secured_loan_inr": 250000000,
            "max_unsecured_loan_inr": 7500000,
            "min_loan_inr": None,
            "interest_rate_secured-upto": "12.75%",
            "interest_rate_unsecured-upto": "12.75%",
            "processing_fee": "1% + GST",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 6 months",
            "repayment_options": ["SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": [
                "US", "UK", "Canada", "Ireland", "Finland", "Denmark", "Sweden", "Spain",
                "Netherlands", "France", "Switzerland", "Belgium", "Austria", "Norway", "Poland",
                "Australia", "Newzealand", "Germany", "Singapore", "Malaysia", "Hong Kong", "Dubai"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": True,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 0,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 30,
            "Foir": [{"Salaried": "75%"}, {"Self Employed": "80%"}],
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 35000,
                "self_employed_inr_annual": 450000
            },
            "own_house_required": True,
            "requires_collateral": None,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "CSIS for income < ₹4.5L",
            "cibil_score_requirement": "720+ preferred",
            "notes": "Private bank offering competitive rates, flexible collateral options."
        }
    },
    {
        "vendorName": "avanse",
        "vendorType": "NBFC",
        "active": True,
        "criteria": {
            "loan_options": ["Secured & Unsecured"],
            "max_secured_loan_inr": 20000000,
            "max_unsecured_loan_inr": 15000000,
            "min_loan_inr": None,
            "interest_rate_secured": "10.5%",
            "interest_rate_unsecured": "11.25%",
            "processing_fee": "1% to 1.5% + GST",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": [
                "US", "UK", "Canada", "Ireland", "Finland", "Denmark", "Italy", "Sweden", "Spain",
                "Netherlands", "France", "Switzerland", "Belgium", "Austria", "Norway", "Poland",
                "Greece", "Malta", "Australia", "Newzealand", "Germany", "South Africa", "Singapore",
                "Malaysia", "Hong Kong"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": True,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "Foir": "50%",
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 33,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 20000,
                "self_employed_inr_annual": 300000
            },
            "own_house_required": True,
            "requires_collateral": None,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": ["Punjab", "Gujarat", "North Eastern States", "J&K"],
            "interest_subsidy_eligibility": "None",
            "cibil_score_requirement": "700+ preferred",
            "notes": "NBFC with flexible loan options, geographical restrictions apply."
        }
    },
    {
        "vendorName": "Tata Capital",
        "vendorType": "NBFC",
        "active": True,
        "criteria": {
            "loan_options": ["Unsecured"],
            "max_secured_loan_inr": None,
            "max_unsecured_loan_inr": 7000000,
            "min_loan_inr": 700000,
            "interest_rate_secured": None,
            "interest_rate_unsecured": "11.5%",
            "processing_fee": "1% + GST",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": [
                "US", "UK", "Canada", "Ireland", "Finland", "Denmark", "Italy", "Sweden", "Spain",
                "Netherlands", "France", "Switzerland", "Belgium", "Austria", "Norway", "Poland",
                "Ukraine", "Greece", "Malta", "Australia", "Newzealand", "Germany"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "Management"],
            "requires_admission": True,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 35,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 25000,
                "self_employed_inr_annual": 300000
            },
            "own_house_required": True,
            "requires_collateral": False,
            "supported_collateral_types": False,
            "geographical_restrictions": False,
            "interest_subsidy_eligibility": "None",
            "cibil_score_requirement": "700+ preferred",
            "notes": "NBFC focused on unsecured loans, requires admission confirmation."
        }
    },
    {
        "vendorName": "unionbank",
        "vendorType": "PSU",
        "active": True,
        "criteria": {
            "loan_options": ["Secured & Unsecured"],
            "max_secured_loan_inr": 15000000,
            "max_unsecured_loan_inr": 4000000,
            "min_loan_inr": None,
            "interest_rate_secured": "9.25%",
            "interest_rate_unsecured": "9.75%",
            "processing_fee": "10000 to 20000",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["SI & EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 15,
            "supported_countries": [
                "US", "UK", "Canada", "Ireland", "Finland", "Denmark", "Italy", "Sweden", "Spain",
                "Netherlands", "France", "Switzerland", "Belgium", "Austria", "Norway", "Poland",
                "Greece", "Malta", "Australia", "Newzealand", "Germany", "South Africa", "Singapore",
                "Malaysia", "Hong Kong"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": True,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 5,
            "min_ielts_score": None,
            "min_toefl_score": None,
            "min_gmat_score": None,
            "min_pte_score": None,
            "min_sat_score": None,
            "min_duolingo_score": None,
            "max_student_age": 40,
            "requires_co_applicant": True,
            "Foir": "60%",
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 20000,
                "self_employed_inr_annual": None
            },
            "own_house_required": True,
            "requires_collateral": None,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "CSIS for income < ₹4.5L",
            "cibil_score_requirement": "None",
            "notes": "PSU bank with flexible loan options, margin money required."
        }
    },
    {
        "vendorName": "Avanse Global",
        "vendorType": "International",
        "active": True,
        "criteria": {
            "loan_options": ["Unsecured"],
            "max_secured_loan_inr": None,
            "max_unsecured_loan_usd": 125000,
            "min_loan_inr": None,
            "interest_rate_secured": None,
            "interest_rate_unsecured": [{"Stem": "10.5% to 13.5%"}, {"Management": "11% to 14%"}],
            "processing_fee": "2.5% + GST",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 6 months",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": ["US"],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "Management"],
            "requires_admission": True,
            "min_academic_score_percentage": None,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 55,
            "requires_co_applicant": False,
            "supported_co_applicant_relations": None,
            "basic_income_norms": None,
            "own_house_required": False,
            "requires_collateral": False,
            "supported_collateral_types": False,
            "geographical_restrictions": False,
            "interest_subsidy_eligibility": "None",
            "cibil_score_requirement": "700+ preferred",
            "notes": "International lender for US only, no co-applicant required."
        }
    },
    {
        "vendorName": "HDFC Credila",
        "vendorType": "NBFC",
        "active": True,
        "criteria": {
            "loan_options": ["Secured & Unsecured"],
            "max_secured_loan_inr": 30000000,
            "max_unsecured_loan_inr": 7500000,
            "min_loan_inr": None,
            "interest_rate_secured": "10.25%",
            "interest_rate_unsecured": "11%",
            "processing_fee": "1% + GST",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 6 months",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": [
                "US", "UK", "Ireland", "Germany", "Canada", "Australia", "Newzealand",
                "South Africa", "Singapore", "Malaysia", "Hong Kong", "Dubai", "Rest of Europe"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": [
                {"Conditional Admission": True}, {"Admission letter not recived": False}, {"Admission Letter": True}
            ],
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 35,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 35000,
                "self_employed_inr_annual": 450000
            },
            "own_house_required": False,
            "requires_collateral": None,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "None",
            "cibil_score_requirement": "700+ preferred",
            "notes": "NBFC with wide country support, competitive rates."
        }
    },
    {
        "vendorName": "InCred",
        "vendorType": "NBFC",
        "active": True,
        "criteria": {
            "loan_options": ["Unsecured"],
            "max_secured_loan_inr": None,
            "max_unsecured_loan_inr": 10000000,
            "min_loan_inr": 1500000,
            "interest_rate_secured": None,
            "interest_rate_unsecured": "11%",
            "processing_fee": "0.75% + GST",
            "loan_tenor_years": "13 to 15",
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": ["US", "Canada", "Germany", "France", "UK", "Newzealand"],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": False,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 33,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 25000,
                "self_employed_inr_annual": 300000
            },
            "own_house_required": False,
            "requires_collateral": False,
            "supported_collateral_types": [],
            "geographical_restrictions": ["J&K", "North Eastern States"],
            "interest_subsidy_eligibility": "None",
            "cibil_score_requirement": "700+ preferred",
            "notes": "NBFC with unsecured focus, geographical restrictions apply."
        }
    },
    {
        "vendorName": "IDFC Bank",
        "vendorType": "Private",
        "active": True,
        "criteria": {
            "loan_options": ["Secured", "Unsecured"],
            "max_secured_loan_inr": 20000000,
            "max_unsecured_loan_inr": 10000000,
            "min_loan_inr": 700000,
            "interest_rate_secured": "9%",
            "interest_rate_unsecured": "11%",
            "processing_fee": "1% + GST",
            "loan_tenor_years": 12,
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "Foir": [{"Salaried": "50%"}, {"Self Employed": "60%"}],
            "supported_countries": [
                "US", "UK", "Ireland", "Germany", "Canada", "Australia", "Newzealand",
                "South Africa", "Singapore", "Malaysia", "Hong Kong"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": False,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 30,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 30000,
                "self_employed_inr_annual": 600000
            },
            "own_house_required": True,
            "requires_collateral": None,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": ["Serviceable pincodes only"],
            "interest_subsidy_eligibility": "CSIS for income < ₹4.5L",
            "cibil_score_requirement": "700+ preferred",
            "notes": "Private bank with pincode restrictions, competitive rates."
        }
    },
    {
        "vendorName": "yesbank",
        "vendorType": "Private",
        "active": True,
        "criteria": {
            "loan_options": ["Secured", "Unsecured"],
            "max_secured_loan_inr": 15000000,
            "max_unsecured_loan_inr": 7500000,
            "min_loan_inr": 700000,
            "interest_rate_secured": "10.5%",
            "interest_rate_unsecured": "11.5%",
            "processing_fee": "1% + GST",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 6 months",
            "repayment_options": ["SI", "EMI", "PSI"],
            "prepayment_penalty": "None",
            "Foir": "60%",
            "margin_money_percentage": 10,
            "supported_countries": [
                "US", "UK", "Ireland", "Germany", "Canada", "Australia", "Newzealand",
                "South Africa", "Singapore", "Malaysia", "Hong Kong", "Dubai"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": False,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 30,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 35000,
                "self_employed_inr_annual": 450000
            },
            "own_house_required": True,
            "requires_collateral": None,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "CSIS for income < ₹4.5L",
            "cibil_score_requirement": "700+ preferred",
            "notes": "Private bank with margin money requirement."
        }
    },
    {
        "vendorName": "Bank of Maharashtra",
        "vendorType": "PSU",
        "active": True,
        "criteria": {
            "loan_options": ["Secured"],
            "max_secured_loan_inr": 25000000,
            "max_unsecured_loan_inr": None,
            "min_loan_inr": None,
            "interest_rate_secured": "9.75%",
            "interest_rate_unsecured": None,
            "processing_fee": "0.5%",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 15,
            "supported_countries": [],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": False,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 30,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 20000,
                "self_employed_inr_annual": None
            },
            "own_house_required": False,
            "requires_collateral": True,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "CSIS for income < ₹4.5L",
            "cibil_score_requirement": "None",
            "notes": "PSU bank, secured loans only, margin money required."
        }
    },
    {
        "vendorName": "bankofbaroda",
        "vendorType": "PSU",
        "active": True,
        "criteria": {
            "loan_options": ["Secured"],
            "max_secured_loan_inr": 15000000,
            "max_unsecured_loan_inr": None,
            "min_loan_inr": None,
            "interest_rate_secured": "9.7%",
            "interest_rate_unsecured": None,
            "processing_fee": "₹10000",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 15,
            "supported_countries": [
                "US", "UK", "Ireland", "Germany", "Canada", "Australia", "Newzealand",
                "South Africa", "Singapore", "Malaysia", "Hong Kong", "All countries"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": False,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 30,
            "Foir": "50%",
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 20000,
                "self_employed_inr_annual": None
            },
            "own_house_required": False,
            "requires_collateral": True,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "CSIS for income < ₹4.5L",
            "cibil_score_requirement": "None",
            "notes": "PSU bank, secured loans up to ₹150L, margin money required."
        }
    },
    {
        "vendorName": "Prodigy",
        "vendorType": "International",
        "active": True,
        "criteria": {
            "loan_options": ["Unsecured"],
            "max_secured_loan_inr": None,
            "max_unsecured_loan_usd": 220000,
            "min_loan_inr": None,
            "interest_rate_secured": None,
            "interest_rate_unsecured": "9.99%",
            "processing_fee": "5% on disbursement",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 6 months",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": ["US", "UK", "Australia", "Ireland", "France"],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": True,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 55,
            "requires_co_applicant": False,
            "supported_co_applicant_relations": None,
            "basic_income_norms": None,
            "own_house_required": False,
            "requires_collateral": False,
            "supported_collateral_types": [],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "None",
            "cibil_score_requirement": "700+ preferred",
            "notes": "International lender, no co-applicant required."
        }
    },
    {
        "vendorName": "mpower",
        "vendorType": "International",
        "active": True,
        "criteria": {
            "loan_options": ["Unsecured"],
            "max_secured_loan_inr": None,
            "max_unsecured_loan_usd": 100000,
            "min_loan_inr": 700000,
            "interest_rate_secured": None,
            "interest_rate_unsecured": "12.99% ",
            "processing_fee": "5%",
            "loan_tenor_years": 10,
            "moratorium_period": "Course duration + 6 months",
            "repayment_options": ["SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": ["US", "Canada"],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": True,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 55,
            "requires_co_applicant": False,
            "supported_co_applicant_relations": None,
            "basic_income_norms": None,
            "own_house_required": False,
            "requires_collateral": False,
            "supported_collateral_types": [],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "None",
            "cibil_score_requirement": "700+ preferred",
            "notes": "International lender for US/Canada, min loan ₹1.66L."
        }
    },
    {
        "vendorName": "Punjab National Bank",
        "vendorType": "PSU",
        "active": True,
        "criteria": {
            "loan_options": ["Secured"],
            "max_secured_loan_inr": 50000000,
            "max_unsecured_loan_inr": None,
            "min_loan_inr": None,
            "interest_rate_secured": "10.5%",
            "interest_rate_unsecured": None,
            "processing_fee": None,
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": [
                "US", "UK", "Canada", "Ireland", "Finland", "Denmark", "Italy", "Sweden", "Spain",
                "Netherlands", "France", "Switzerland", "Belgium", "Austria", "Norway", "Poland",
                "Ukraine", "Greece", "Malta", "Australia", "Newzealand", "Germany", "South Africa",
                "Singapore", "Malaysia", "Hong Kong", "All countries"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": True,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 30,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": ["Father", "Mother", "Husband", "Wife", "Brother", "Sister"],
            "basic_income_norms": {
                "salaried_inr_monthly": 20000,
                "self_employed_inr_annual": None
            },
            "own_house_required": False,
            "requires_collateral": True,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": [],
            "interest_subsidy_eligibility": "CSIS for income < ₹4.5L",
            "cibil_score_requirement": "None",
            "notes": "PSU bank with high secured loan limit, competitive rates."
        }
    },
    {
        "vendorName": "auxilo",
        "vendorType": "NBFC",
        "active": True,
        "criteria": {
            "loan_options": ["Secured", "Unsecured"],
            "max_secured_loan_inr": 20000000,
            "max_unsecured_loan_inr": 10000000,
            "min_loan_inr": 700000,
            "interest_rate_secured": "11%",
            "interest_rate_unsecured": "11.25%",
            "processing_fee": "1%",
            "loan_tenor_years": 15,
            "moratorium_period": "Course duration + 1 year",
            "repayment_options": ["PSI", "SI", "EMI"],
            "prepayment_penalty": "None",
            "margin_money_percentage": 0,
            "supported_countries": [
                "US", "UK", "Ireland", "Germany", "Canada", "Australia", "Newzealand",
                "Rest of Europe", "Singapore"
            ],
            "supported_degrees": ["Masters", "Bachelors", "PgDiploma"],
            "supported_courses": ["Stem", "NonStem", "Management"],
            "requires_admission": False,
            "min_academic_score_percentage": 60,
            "max_educational_backlogs": 15,
            "min_ielts_score": 6,
            "min_toefl_score": 80,
            "min_gmat_score": 400,
            "min_pte_score": 51,
            "min_sat_score": 1000,
            "min_duolingo_score": 106,
            "max_student_age": 30,
            "requires_co_applicant": True,
            "supported_co_applicant_relations": [
                "Father", "Mother", "Husband", "Wife", "Brother", "Sister", "1st Cousin",
                "Uncle", "Aunt", "Father in Law", "Mother in Law", "Brother in Law"
            ],
            "basic_income_norms": {
                "salaried_inr_monthly": 25000,
                "self_employed_inr_annual": 300000
            },
            "own_house_required": True,
            "requires_collateral": None,
            "supported_collateral_types": ["Property", "Fixed Deposit"],
            "geographical_restrictions": ["Uttar Pradesh", "Bihar", "North Eastern States", "J&K", "Kerala"],
            "interest_subsidy_eligibility": "None",
            "cibil_score_requirement": "700+ preferred",
            "notes": "NBFC with flexible loan options, geographical restrictions apply."
        }
    }
]

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

def calculate_foir(
    student_profile: Dict,
    vendor: Dict,
    requested_loan_amount: float,
    interest_rate: Optional[float] = None,
    tenure_years: Optional[float] = None,
    exchange_rate: Optional[float] = None
) -> Tuple[float, float, str]:
    """Calculate FOIR and adjust loan amount with improved EMI and FOIR logic."""
    vendor_name = vendor.get("vendorName", "Unknown")
    logger.info(f"Calculating FOIR for student profile with loan amount: {format_amount(requested_loan_amount)} INR for vendor {vendor_name}")
    
    # Extract co-applicant and student income
    co_applicant_details = student_profile.get("co_applicant_details", {})
    yearly_income = co_applicant_details.get("co_applicant_income_amount", {}).get("amount", 0) if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict) else 0
    currency = co_applicant_details.get("co_applicant_income_amount", {}).get("currency", "INR") if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict) else "INR"
    # Add student income if available (e.g., part-time work)
    student_income = student_profile.get("education_details", {}).get("current_income_amount", {}).get("amount", 0) if isinstance(student_profile.get("education_details", {}).get("current_income_amount"), dict) else 0
    student_currency = student_profile.get("education_details", {}).get("current_income_amount", {}).get("currency", "INR") if isinstance(student_profile.get("education_details", {}).get("current_income_amount"), dict) else "INR"

    # Convert incomes to INR
    exchange_rate = exchange_rate or get_usd_to_inr_rate()
    if currency != "INR":
        yearly_income *= exchange_rate
        logger.info(f"Converted co-applicant income to INR: {format_amount(yearly_income)} for vendor {vendor_name}")
    if student_currency != "INR":
        student_income *= exchange_rate
        logger.info(f"Converted student income to INR: {format_amount(student_income)} for vendor {vendor_name}")
    
    total_yearly_income = yearly_income + student_income
    monthly_income = total_yearly_income / 12 if total_yearly_income > 0 else 0

    # Validate income
    if not total_yearly_income and vendor.get("criteria", {}).get("requires_co_applicant", False):
        logger.warning(f"No income provided for vendor {vendor_name} requiring co-applicant")
        return 0, requested_loan_amount, "No income provided"

    # Extract existing EMI
    existing_emi = co_applicant_details.get("co_applicant_existing_loan_emi_amount", {}).get("amount", 0) if isinstance(co_applicant_details.get("co_applicant_existing_loan_emi_amount"), dict) else 0
    logger.info(f"Existing EMI: {format_amount(existing_emi)} INR for vendor {vendor_name}")

    # Parse FOIR limit
    foir_field = vendor.get("criteria", {}).get("Foir", "75%")
    occupation = co_applicant_details.get("co_applicant_occupation", "Salaried")
    try:
        if isinstance(foir_field, str):
            foir_limit = float(foir_field.strip("%")) / 100
        elif isinstance(foir_field, list):
            foir_limit = 0.75
            for entry in foir_field:
                if entry.get(occupation.lower().capitalize()):
                    foir_limit = float(entry[occupation.lower().capitalize()].strip("%")) / 100
                    break
        elif isinstance(foir_field, dict):
            foir_limit = float(foir_field.get(occupation.lower(), "75%").strip("%")) / 100
        else:
            logger.warning(f"Invalid Foir format for vendor {vendor_name}: {foir_field}, using default 75%")
            foir_limit = 0.75
        foir_limit = min(max(foir_limit, 0.1), 0.9)  # Ensure 10%–90%
        logger.info(f"FOIR limit for {occupation}: {foir_limit*100}%")
    except (ValueError, AttributeError, TypeError) as e:
        logger.error(f"Error parsing Foir for vendor {vendor_name}: {foir_field}, error: {str(e)}, using default 75%")
        foir_limit = 0.75

    # Parse interest rate
    interest_rate = interest_rate or vendor.get("criteria", {}).get("interest_rate_unsecured", 
                            vendor.get("criteria", {}).get("interest_rate_secured", 10.0))
    try:
        if isinstance(interest_rate, str):
            # Handle ranges (e.g., "10.5% to 13.5%") by taking the minimum
            rate_str = interest_rate.replace("–", "-").split("%")[0].split(" to ")[0].split("-")[0].strip()
            interest_rate = float(rate_str)
        elif isinstance(interest_rate, list):
            rate_str = list(interest_rate[0].values())[0].replace("–", "-").split("%")[0].split(" to ")[0].split("-")[0]
            interest_rate = float(rate_str)
        else:
            interest_rate = float(interest_rate)
        interest_rate = min(max(interest_rate, 5.0), 20.0)  # Ensure 5%–20%
        logger.info(f"Interest rate: {interest_rate}%")
    except (ValueError, AttributeError, TypeError, IndexError) as e:
        logger.error(f"Error parsing interest rate for vendor {vendor_name}: {interest_rate}, error: {str(e)}, using default 10%")
        interest_rate = 10.0

    # Parse tenure
    tenure_years = tenure_years or vendor.get("criteria", {}).get("loan_tenor_years", 15)
    try:
        if isinstance(tenure_years, str):
            tenure_years = float(tenure_years.strip().split(" to ")[0].split()[0])
        tenure_years = min(max(tenure_years, 1.0), 20.0)  # Ensure 1–20 years
        logger.info(f"Initial tenure: {tenure_years} years")
    except (ValueError, AttributeError) as e:
        logger.error(f"Error parsing tenure years for vendor {vendor_name}: {tenure_years}, error: {str(e)}, using default 15 years")
        tenure_years = 15.0

    # Validate minimum loan amount
    min_loan_inr = vendor.get("criteria", {}).get("min_loan_inr", 0) or 0
    if requested_loan_amount < min_loan_inr:
        logger.warning(f"Requested loan {format_amount(requested_loan_amount)} INR below minimum {format_amount(min_loan_inr)} for vendor {vendor_name}")
        return 0, requested_loan_amount, f"Loan amount below minimum {format_amount(min_loan_inr)}"

    monthly_rate = interest_rate / (12 * 100)
    tenure_months = tenure_years * 12
    adjusted_loan = requested_loan_amount
    foir = 0
    message = "Loan amount within FOIR limit"
    proposed_emi = 0

    try:
        if total_yearly_income == 0:
            logger.info(f"No FOIR calculation needed for vendor {vendor_name} (no income or not required)")
            return 0, requested_loan_amount, "No FOIR calculation needed (no income or not required)"

        # Calculate initial EMI
        proposed_emi = adjusted_loan * monthly_rate * (1 + monthly_rate) ** tenure_months / ((1 + monthly_rate) ** tenure_months - 1) if monthly_rate > 0 else adjusted_loan / tenure_months
        proposed_emi = round(proposed_emi, 2)
        total_obligations = existing_emi + proposed_emi
        foir = (total_obligations / monthly_income * 100) if monthly_income > 0 else float('inf')
        logger.info(f"Initial EMI: {format_amount(proposed_emi)} INR, FOIR: {foir:.2f}% (limit: {foir_limit*100}%)")

        if foir > foir_limit * 100:
            # Try reducing tenure first
            min_tenure_years = max(1.0, tenure_years - 5)  # Allow reduction up to 5 years
            tenure_years_adjusted = tenure_years
            while tenure_years_adjusted > min_tenure_years and foir > foir_limit * 100:
                tenure_years_adjusted -= 1
                tenure_months = tenure_years_adjusted * 12
                proposed_emi = adjusted_loan * monthly_rate * (1 + monthly_rate) ** tenure_months / ((1 + monthly_rate) ** tenure_months - 1) if monthly_rate > 0 else adjusted_loan / tenure_months
                proposed_emi = round(proposed_emi, 2)
                total_obligations = existing_emi + proposed_emi
                foir = (total_obligations / monthly_income * 100) if monthly_income > 0 else float('inf')
                logger.info(f"Adjusted tenure to {tenure_years_adjusted} years: EMI {format_amount(proposed_emi)} INR, FOIR {foir:.2f}%")

            if foir <= foir_limit * 100:
                message = f"Tenure adjusted to {tenure_years_adjusted} years to meet FOIR limit ({foir_limit*100}%)"
                logger.info(message)
            else:
                # Reduce loan amount
                max_obligations = foir_limit * monthly_income
                max_emi = max_obligations - existing_emi
                if max_emi <= 0:
                    logger.warning(f"Existing obligations exceed FOIR limit for vendor {vendor_name}")
                    return foir, 0, "Existing obligations exceed FOIR limit"
                adjusted_loan = max_emi * ((1 + monthly_rate) ** tenure_months - 1) / (monthly_rate * (1 + monthly_rate) ** tenure_months) if monthly_rate > 0 else max_emi * tenure_months
                adjusted_loan = round(max(adjusted_loan, 0), 2)
                
                if adjusted_loan < min_loan_inr:
                    logger.warning(f"Adjusted loan {format_amount(adjusted_loan)} INR below minimum {format_amount(min_loan_inr)} for vendor {vendor_name}")
                    return foir, adjusted_loan, f"Adjusted loan {format_amount(adjusted_loan)} below minimum {format_amount(min_loan_inr)}"
                
                proposed_emi = max_emi
                foir = (existing_emi + proposed_emi) / monthly_income * 100 if monthly_income > 0 else float('inf')
                message = f"Loan adjusted to INR {format_amount(adjusted_loan)} to meet FOIR limit ({foir_limit*100}%)"
                logger.info(message)

        return foir, adjusted_loan, message
    except Exception as e:
        logger.error(f"Error calculating FOIR for vendor {vendor_name}: {str(e)}")
        return 0, requested_loan_amount, f"Error calculating FOIR: {str(e)}"

def get_llm_vendor_matches(student_profile: Dict, vendors: Optional[List[Dict]] = None) -> Tuple[List[Dict], Optional[str]]:
    """Match student profile with university-specific vendors from MongoDB using OpenAI GPT-4 or mock response."""
    student_id = student_profile.get("student_id", "?")
    logger.info(f"Starting vendor matching for student {student_id}")
    logger.debug(f"Raw student profile: {json.dumps(student_profile, default=str, ensure_ascii=False)}")
    
    # Validate co-applicant details
    if student_profile.get("loan_details", {}).get("co_applicant_available") == "Yes" and not student_profile.get("co_applicant_details"):
        logger.warning("Co-applicant details missing despite co_applicant_available: Yes")
        student_profile["co_applicant_details"] = {
            "co_applicant_occupation": "Salaried",
            "co_applicant_relation": "Unknown"
        }

    # Extract profile details with None checks
    education_details = student_profile.get("education_details", {})
    loan_details = student_profile.get("loan_details", {})
    co_applicant_details = student_profile.get("co_applicant_details", {})
    
    # Define key variables early to avoid undefined errors
    co_applicant_available = loan_details.get("co_applicant_available") == "Yes"
    collateral_available = loan_details.get("collateral_available") == "Yes"
    loan_preference = "Secured" if collateral_available else "Unsecured"
    logger.info(f"Loan preference set to {loan_preference} based on collateral_available: {collateral_available}")
    
    university = education_details.get("university_name", [""])[0] if isinstance(education_details.get("university_name"), list) else ""
    country = education_details.get("study_destination_country", [""])[0] if isinstance(education_details.get("study_destination_country"), list) else ""
    geo_state = student_profile.get("current_location_state", "").upper()
    course_type = education_details.get("course_type", "").replace("-", "")
    intended_degree = education_details.get("intended_degree", "")
    admission_status = education_details.get("admission_status", "")
    academic_score = education_details.get("academic_score", {}).get("value", 0)
    backlogs = education_details.get("educational_backlogs", 0)
    age = (datetime.utcnow().year - int(student_profile.get("date_of_birth", "2000-01-01")[:4])) if student_profile.get("date_of_birth") else None
    cibil_score = loan_details.get("cibil_score", "None")
    co_applicant_occupation = co_applicant_details.get("co_applicant_occupation", "")
    co_applicant_relation = co_applicant_details.get("co_applicant_relation", "")
    co_applicant_income = co_applicant_details.get("co_applicant_income_amount", {}).get("amount", 0) if isinstance(co_applicant_details.get("co_applicant_income_amount"), dict) else 0
    english_test = education_details.get("english_test", {})
    english_test_type = english_test.get("type") if isinstance(english_test, dict) else None
    english_test_score = english_test.get("score") if isinstance(english_test, dict) else None
    standardized_test = education_details.get("standardized_test", {})
    standardized_test_type = standardized_test.get("type") if isinstance(standardized_test, dict) else None
    standardized_test_score = standardized_test.get("score") if isinstance(standardized_test, dict) else None
    course_duration = education_details.get("course_duration", {})
    course_duration_years = float(course_duration.get("years", 0)) + (float(course_duration.get("months", 0)) / 12) if isinstance(course_duration, dict) else 0.0
    collateral_type = loan_details.get("collateral_type")
    collateral_value = loan_details.get("collateral_value_amount", {}).get("amount") if isinstance(loan_details.get("collateral_value_amount"), dict) else None
    collateral_location_state = loan_details.get("collateral_location_state")

    valid_vendors = VENDORS if vendors is None else vendors
    no_university_vendors = False
    university_vendors = []
    if university and universities_collection is not None:
        try:
            university_doc = universities_collection.find_one({"name": {"$regex": f"^{re.escape(university)}$", "$options": "i"}})
            if university_doc and "vendors" in university_doc and university_doc["vendors"]:
                university_vendors = university_doc["vendors"]
                logger.info(f"Found vendors for university {university}: {university_vendors}")
                valid_vendors = [
                    v for v in valid_vendors
                    if any(v["vendorName"].lower().replace("-", "") == uv.lower().replace("-", "") for uv in university_vendors)
                ]
                logger.info(f"Filtered to {len(valid_vendors)} university-specific vendors: {[v['vendorName'] for v in valid_vendors]}")
            else:
                logger.warning(f"No vendors found for university {university} in MongoDB; using static vendor list")
                no_university_vendors = True
                logger.info(f"Static vendors considered: {[v['vendorName'] for v in valid_vendors]}")
        except Exception as e:
            logger.error(f"Error querying MongoDB for university {university}: {str(e)}")
            no_university_vendors = True

    if not valid_vendors:
        logger.error("No vendors available for matching")
        return [], "No vendors configured"

    # Filter vendors by country and geographical restrictions
    logger.info(f"Filtering vendors for country {country} and geo {geo_state}{' (no university vendors)' if no_university_vendors else ''}")
    filtered_vendors = []
    for vendor in valid_vendors:
        vendor_name = vendor.get("vendorName")
        criteria = vendor.get("criteria", {})
        country_supported = country in criteria.get("supported_countries", [])
        geo_restrictions = criteria.get("geographical_restrictions", []) or [] if isinstance(criteria.get("geographical_restrictions"), list) else []
        geo_restricted = any(geo_state in restriction.upper() for restriction in geo_restrictions)
        if country_supported and not geo_restricted:
            filtered_vendors.append(vendor)
            logger.info(f"Vendor {vendor_name} passed country ({country}) and geo ({geo_state}) filters")
        else:
            logger.info(f"Vendor {vendor_name} filtered out: country_supported={country_supported}, geo_restricted={geo_restricted}")

    valid_vendors = filtered_vendors
    logger.info(f"Filtered to {len(valid_vendors)} country-supported vendors: {[v['vendorName'] for v in valid_vendors]}")

    # Convert loan amount
    try:
        loan_details = loan_details.get("loan_amount_requested", education_details.get("loan_amount_requested", {}))
        if not isinstance(loan_details, dict):
            logger.error(f"Invalid loan_amount_requested structure: {loan_details}, type: {type(loan_details)}")
            raise ValueError("loan_amount_requested must be a dictionary")
        raw_amount = loan_details.get("amount")
        currency = loan_details.get("currency", "INR")
        logger.debug(f"Raw loan amount: {raw_amount}, type: {type(raw_amount)}, currency: {currency}")
        
        if raw_amount is None:
            logger.error("Loan amount is None in loan_amount_requested")
            raise ValueError("Loan amount cannot be None")
        
        try:
            loan_amount = float(raw_amount)
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert loan amount '{raw_amount}' to float: {str(e)}")
            raise ValueError(f"Invalid loan amount format: {raw_amount}")
        
        if loan_amount <= 0:
            logger.error(f"Loan amount is non-positive: {loan_amount}")
            raise ValueError("Loan amount must be positive")
        
        if currency == "USD":
            exchange_rate = get_usd_to_inr_rate()
            loan_amount *= exchange_rate
            logger.info(f"Converted USD {loan_amount/exchange_rate:.2f} to INR {loan_amount:.2f} (rate: {exchange_rate})")
        logger.info(f"Final loan amount: {format_amount(loan_amount)} INR")
    except ValueError as e:
        logger.error(f"Error parsing loan amount: {str(e)}")
        return [], f"Failed to parse loan amount: {str(e)}"

    # Log strict matching step
    logger.info("### Step 1: Strict Matching")
    logger.info(f"Profile:\n"
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
                f"  - Loan Preference: {loan_preference}")

    logger.info("Vendors:")
    eligible_vendors = []
    if no_university_vendors:
        eligible_vendors = valid_vendors
        logger.info(f"No vendors for university {university}; sending {len(eligible_vendors)} vendors to LLM for scoring: {[v['vendorName'] for v in eligible_vendors]}")
    else:
        for vendor in valid_vendors:
            vendor_name = vendor.get("vendorName")
            criteria = vendor.get("criteria", {})
            reasons = []
            is_eligible = True

            logger.info(f"{vendor_name}:")

            try:
                # Check country (already filtered)
                logger.info(f"  - Supported Country: Yes")

                # Check degree
                if intended_degree and intended_degree not in criteria.get("supported_degrees", []):
                    reasons.append(f"Intended degree {intended_degree} not in supported_degrees")
                    is_eligible = False
                    logger.info(f"  - Supported Degree: No")
                else:
                    logger.info(f"  - Supported Degree: Yes")

                # Check loan amount
                max_unsecured_inr = criteria.get("max_unsecured_loan_inr")
                max_unsecured_usd = criteria.get("max_unsecured_loan_usd")
                if max_unsecured_usd:
                    max_unsecured_inr = max_unsecured_usd * get_usd_to_inr_rate()
                max_secured_inr = criteria.get("max_secured_loan_inr")
                if loan_preference == "Unsecured" and max_unsecured_inr and loan_amount > max_unsecured_inr:
                    reasons.append(f"Loan amount {format_amount(loan_amount)} exceeds max_unsecured_loan_inr {format_amount(max_unsecured_inr)}")
                    is_eligible = False
                    logger.info(f"  - Loan Amount: Exceeds max unsecured loan")
                elif loan_preference == "Secured" and max_secured_inr and loan_amount > max_secured_inr:
                    reasons.append(f"Loan amount {format_amount(loan_amount)} exceeds max_secured_loan_inr {format_amount(max_secured_inr)}")
                    is_eligible = False
                    logger.info(f"  - Loan Amount: Exceeds max secured loan")
                else:
                    logger.info(f"  - Loan Amount: Meets max {loan_preference.lower()} loan")

                # Check CIBIL score
                cibil_requirement = criteria.get("cibil_score_requirement", "None")
                cibil_ok = cibil_requirement == "None" or (cibil_requirement == "700+ preferred" and (cibil_score == "None" or (isinstance(cibil_score, str) and cibil_score.isdigit() and int(cibil_score) >= 700)))
                if not cibil_ok:
                    reasons.append(f"CIBIL score {cibil_score} does not meet requirement {cibil_requirement}")
                    is_eligible = False
                    logger.info(f"  - CIBIL Score: Does not meet requirement")
                else:
                    logger.info(f"  - CIBIL Score: Meets requirement")

                # Check loan preference
                loan_options = criteria.get("loan_options", [])
                if isinstance(loan_options, list):
                    # Handle dicts in list
                    if any(isinstance(opt, dict) for opt in loan_options):
                        loan_options = [list(opt.keys())[0] for opt in loan_options]
                    else:
                        # Split combined strings like "Secured & Unsecured"
                        flattened_options = []
                        for opt in loan_options:
                            flattened_options.extend([o.strip() for o in opt.split("&")])
                        loan_options = flattened_options
                elif isinstance(loan_options, str):
                    loan_options = [opt.strip() for opt in loan_options.split("&")]
                if loan_preference == "Unsecured" and not any(opt in ["Unsecured", "Secured & Unsecured"] for opt in loan_options):
                    reasons.append(f"Loan preference {loan_preference} not in loan_options")
                    is_eligible = False
                    logger.info(f"  - Loan Preference: Does not match unsecured")
                elif loan_preference == "Secured" and not any(opt in ["Secured", "Secured & Unsecured"] for opt in loan_options):
                    reasons.append(f"Loan preference {loan_preference} not in loan_options")
                    is_eligible = False
                    logger.info(f"  - Loan Preference: Does not match secured")
                else:
                    logger.info(f"  - Loan Preference: Matches {loan_preference.lower()}")

                # Check co-applicant
                supported_relations = criteria.get("supported_co_applicant_relations", []) or []
                if criteria.get("requires_co_applicant") and not co_applicant_available:
                    reasons.append("Co-applicant required but not available")
                    is_eligible = False
                    logger.info(f"  - Co-Applicant: Required but not available")
                elif criteria.get("requires_co_applicant") and co_applicant_relation and co_applicant_relation not in supported_relations:
                    reasons.append(f"Co-applicant relation {co_applicant_relation} not supported")
                    is_eligible = False
                    logger.info(f"  - Co-Applicant: Relation not supported")
                else:
                    logger.info(f"  - Co-Applicant: {'Available' if co_applicant_available else 'Not required'}")

                # Check collateral availability (skip type check)
                requires_collateral = criteria.get("requires_collateral")
                if requires_collateral is None:
                    requires_collateral = True if loan_preference == "Secured" else False
                if requires_collateral and not collateral_available:
                    reasons.append("Collateral required but not available")
                    is_eligible = False
                    logger.info(f"  - Collateral: Required but not available")
                else:
                    logger.info(f"  - Collateral: {'Not required' if not requires_collateral else 'Available'}")

                # Log secondary criteria (non-exclusionary)
                supported_courses = [c.replace("-", "") for c in criteria.get("supported_courses", [])]
                course_match = course_type.lower() in [sc.lower() for sc in supported_courses]
                logger.info(f"  - Supported Courses: {'Yes' if course_match else 'No'}")

                requires_admission = criteria.get("requires_admission")
                admission_ok = True
                if isinstance(requires_admission, bool):
                    admission_ok = not requires_admission or admission_status in ["Admission letter received", "Conditional letter received"]
                elif isinstance(requires_admission, list):
                    admission_ok = any(
                        entry.get("Admission Letter") or entry.get("Conditional Admission")
                        for entry in requires_admission
                    ) and admission_status in ["Admission letter received", "Conditional letter received"]
                elif requires_admission is not None:
                    logger.warning(f"Invalid requires_admission format for vendor {vendor_name}: {requires_admission}")
                    admission_ok = False
                logger.info(f"  - Requires Admission: {'Yes' if admission_ok else 'No'}")

                academic_ok = not criteria.get("min_academic_score_percentage") or academic_score >= criteria.get("min_academic_score_percentage")
                logger.info(f"  - Academic Score: {'Meets requirement' if academic_ok else 'Below minimum'}")

                age_ok = not criteria.get("max_student_age") or (age and age <= criteria.get("max_student_age"))
                logger.info(f"  - Age: {'Within limit' if age_ok else 'Exceeds maximum'}")

                backlogs_ok = criteria.get("max_educational_backlogs") is None or backlogs <= criteria.get("max_educational_backlogs")
                logger.info(f"  - Backlogs: {'Within limit' if backlogs_ok else 'Exceeds maximum'}")

                if is_eligible:
                    eligible_vendors.append(vendor)
                    logger.info(f"  - Match: Yes")
                else:
                    logger.info(f"  - Match: No ({', '.join(reasons)})")
            except Exception as e:
                logger.error(f"Error checking eligibility for vendor {vendor_name}: {str(e)}")
                logger.info(f"  - Match: No (Error: {str(e)})")

    valid_vendors = eligible_vendors
    logger.info(f"Eligible vendors for LLM: {len(valid_vendors)} - {[v['vendorName'] for v in valid_vendors]}")

    # FOIR calculation step
    logger.info("### Step 2: FOIR Calculation")
    foir_results = {}
    for vendor in valid_vendors:
        vendor_name = vendor.get("vendorName")
        foir, adjusted_loan, foir_message = calculate_foir(student_profile, vendor, loan_amount)
        foir_results[vendor_name] = {"foir": foir, "adjusted_loan": adjusted_loan, "message": foir_message}
        interest_rate = vendor["criteria"].get("interest_rate_secured" if loan_preference == "Secured" else "interest_rate_unsecured", 
                         vendor["criteria"].get("interest_rate_unsecured_upto", 
                         vendor["criteria"].get("interest_rate_secured", "N/A")))
        logger.info(f"{vendor_name}:\n"
                    f"  - Interest Rate: {interest_rate}\n"
                    f"  - Proposed EMI: {format_amount(adjusted_loan)} INR\n"
                    f"  - FOIR: {foir:.2f}%\n"
                    f"  - FOIR Suggestion: {foir_message}")

    # Mock response if no API key
    if not OPENAI_API_KEY:
        logger.warning("OpenAI API key missing, using mock response")
        mock_matches = [
            {
                "vendor_id": v.get("vendorName").replace(" ", "_").lower(),
                "vendor_name": v.get("vendorName"),
                "match_type": "Best Match",
                "score": 80,
                "reason": "Mock match due to missing API key",
                "adjusted_loan_amount_inr": foir_results.get(v.get("vendorName"), {}).get("adjusted_loan", loan_amount),
                "interest_rate": v.get("criteria", {}).get("interest_rate_secured" if loan_preference == "Secured" else "interest_rate_unsecured", "9.75%"),
                "loan_tenor": v.get("criteria", {}).get("loan_tenor_years", 15),
                "processing_fee": v.get("criteria", {}).get("processing_fee", "0.5%"),
                "moratorium_period": v.get("criteria", {}).get("moratorium_period", "Course duration + 1 year"),
                "repayment_options": v.get("criteria", {}).get("repayment_options", ["EMI"]),
                "foir_suggestion": foir_results.get(v.get("vendorName"), {}).get("message", "Mock FOIR within limit")
            } for v in valid_vendors[:2]
        ]
        logger.info("### Step 3: Weightage-Based Ranking")
        for match in mock_matches:
            logger.info(f"{match['vendor_name']}:\n"
                        f"  - Score: {match['score']}\n"
                        f"  - Reason: {match['reason']}")
        logger.info("### Final Output")
        logger.info(json.dumps({"matches": mock_matches, "summary_text": "Mock matching completed due to missing API key", "fallback": no_university_vendors}, indent=2))
        logger.info(f"Final response: {len(mock_matches)} matches, fallback={no_university_vendors}")
        return mock_matches, "Mock matching completed due to missing API key"

    # Prepare LLM input
    profile_summary = {
        "Dest Country": country,
        "Dest Countries": student_profile.get("education_details", {}).get("study_destination_country", []),
        "Intended Degree": intended_degree,
        "University": university,
        "Universities": student_profile.get("education_details", {}).get("university_name", []),
        "Course Category": course_type,
        "Loan Amount INR": loan_amount,
        "Collateral Available": collateral_available,
        "Collateral Type": collateral_type,
        "Collateral Value INR": collateral_value,
        "Collateral Location State": collateral_location_state,
        "Co-Applicant Available": co_applicant_available,
        "Co-Applicant Relation": co_applicant_relation,
        "Co-Applicant Occupation": co_applicant_occupation,
        "Co-Applicant Income INR (Annual)": co_applicant_income,
        "Co-Applicant Existing EMI INR": co_applicant_details.get("co_applicant_existing_loan_emi_amount", {}).get("amount", 0) if isinstance(co_applicant_details.get("co_applicant_existing_loan_emi_amount"), dict) else 0,
        "Co-Applicant EMI Default": "Yes" if co_applicant_details.get("co_applicant_emi_default") == "Yes" else "No",
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
        "Loan Preference": loan_preference,
        "Geo State": geo_state
    }
    logger.info(f"Profile summary for matching: {json.dumps(profile_summary, default=str, ensure_ascii=False)}")

    vendor_details_list = [
        {
            "id": v.get("vendorName").replace(" ", "_").lower(),
            "name": v.get("vendorName"),
            "criteria": {k: v for k, v in v.get("criteria", {}).items() if v is not None}
        }
        for v in valid_vendors
    ]
    vendors_str = json.dumps(vendor_details_list, ensure_ascii=False)
    logger.info(f"Prepared vendor data for LLM: {len(vendor_details_list)} vendors")

    # LLM prompt
    prompt = f"""Analyze the student profile against vendors, prioritizing country, loan type, and other primary criteria, with education details as secondary.

Profile: {json.dumps(profile_summary, ensure_ascii=False)}
Vendors: {vendors_str}

Task:
1. **Primary Matching** (Mandatory for Inclusion):
   - Country: Dest Country must be in supported_countries.
   - Loan Amount: Loan Amount INR must be <= max_unsecured_loan_inr (for Unsecured) or max_secured_loan_inr (for Secured, convert max_unsecured_loan_usd to INR using 83.0 rate if not provided).
   - Geo Restrictions: Geo State must not be in geographical_restrictions.
   - Collateral (for Secured): Collateral Available must be true if requires_collateral is true or null and Loan Preference is Secured (do not check Collateral Type).

2. **Scoring** (100 points):
   - University Vendor List: +20 if vendor is in university's MongoDB vendor list {university_vendors}, +0 if not.
   - Loan Amount After FOIR: +15 if loan amount (or adjusted after FOIR) meets limits, +7 if within 10% of requested amount, +0 if exceeds or adjusted to 0.
   - Supported Country: +10 if Dest Country matches supported_countries.
   - Supported Course Type: +10 if Course Category matches supported_courses (case-insensitive, ignore hyphens).
   - Collateral: +8 if Collateral Available and Loan Preference is Secured, +0 if not.
   - Loan Type: +7 if Loan Preference and Collateral Available align with loan_options (Unsecured if Collateral Available=false, Secured if true).
   - Admission Status: +5 if requires_admission is true (boolean or list with 'Admission Letter'/'Conditional Admission') and Admission Status is 'Admission letter received' or 'Conditional letter received', +0 if not or requires_admission=False.
   - Co-Applicant Salaried: +3 if Co-Applicant Available, requires_co_applicant=True, and Co-Applicant Occupation is 'Salaried', +0 if not.
   - FOIR Score: +2 if FOIR is within limit, +0 if not.
   - Past Education Details: +10 total (+5 if Academic Score meets min_academic_score_percentage, +3 if English Test meets minimum or None and not required, +2 if Standardized Test meets minimum or not required).
   - Backlogs: +5 if Backlogs <= max_educational_backlogs, +0 if exceeds.
   - Age and Others: +5 total (+2 if Age <= max_student_age, +2 if margin money requirement met (assume 0% if unspecified), +1 if CIBIL Score meets cibil_score_requirement (assume 700 if 'preferred')).

3. **FOIR Calculation**:
   - Calculate FOIR using Co-Applicant Income INR (Annual) and Co-Applicant Existing EMI INR.
   - FOIR = (Existing EMI + Proposed EMI) / Monthly Income * 100.
   - Proposed EMI = Loan Amount INR * r * (1+r)^n / ((1+r)^n - 1), where r = interest_rate/12/100, n = loan_tenor_years*12.
   - Use interest_rate_secured (for Secured) or interest_rate_unsecured (for Unsecured) based on Loan Preference.
   - FOIR Limit: Use Foir value based on Co-Applicant Occupation (default 75% for Salaried).
   - Adjust Loan Amount INR if FOIR exceeds limit, respecting min_loan_inr.
   - Skip FOIR if no co-applicant required or income missing.

4. **Output**:
   - Return ONLY a valid JSON object: {{"matches": [...], "summary_text": "...", "fallback": {no_university_vendors}}}.
   - Include vendors with score >= 50.
   - Match Type: "Best Match" for score >= 80, "Near Match" for 50-79, "No Match" for <50.
   - Structure: {{"vendor_id": "<id>", "vendor_name": "<name>", "match_type": "Best Match|Near Match|No Match", "score": 0-100, "reason": "Matched primary: country (UK), loan type (Secured), loan amount; Secondary: missing English test (-3 points)", "adjusted_loan_amount_inr": FLOAT, "interest_rate": "X%", "loan_tenor": INT, "processing_fee": "X%", "moratorium_period": "...", "repayment_options": [...], "foir_suggestion": "..."}}.
   - Provide detailed reasons for scores, noting primary matches (e.g., country, loan type) and secondary failures (e.g., education details).
   - Set "fallback": true if no university vendors were found in MongoDB.
"""
    logger.info("Sending prompt to OpenAI GPT-3.5-turbo API")
    max_retries = 2
    for attempt in range(max_retries):
        try:
            chat_response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Loan matching assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=14000,
                response_format={"type": "json_object"}
            )
            raw_content = chat_response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            if json_match:
                raw_content = json_match.group(0)
            else:
                logger.error("No JSON found in GPT-4 response")
                raise ValueError("No valid JSON in GPT-4 response")
            logger.info(f"Raw GPT-4 response: {raw_content}")

            try:
                parsed_json = json.loads(raw_content)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response from GPT-4: {str(e)}")
                raise ValueError("Invalid JSON response from GPT-4")

            logger.info(f"Parsed GPT-4 response: {parsed_json.get('summary_text')}")
            parsed_json["fallback"] = no_university_vendors

            # Log weightage-based ranking
            logger.info("### Step 3: Weightage-Based Ranking")
            for match in parsed_json.get("matches", []):
                logger.info(f"{match['vendor_name']}:\n"
                            f"  - Score: {match['score']}\n"
                            f"  - Reason: {match['reason']}")

            # Filter matches with score >= 50
            matches = [match for match in parsed_json.get("matches", []) if match["score"] >= 50]
            for match in parsed_json.get("matches", []):
                log_level = logger.info if match["score"] >= 50 else logger.debug
                log_level(f"Vendor match: {match['vendor_name']} - {match['match_type']} (Score: {match['score']}, Reason: {match['reason']}, FOIR: {match['foir_suggestion']})")

            # Log final output
            logger.info("### Final Output")
            logger.info(json.dumps({"matches": matches, "summary_text": parsed_json.get("summary_text", "Matching done"), "fallback": no_university_vendors}, indent=2))

            logger.info(f"Final response: {len(matches)} matches, fallback={no_university_vendors}")
            return matches, parsed_json.get("summary_text", "Matching done")
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{max_retries} failed: Error processing GPT-4 vendor match response: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            logger.warning("Falling back to manual response due to API failure")
            manual_matches = [
                {
                    "vendor_id": v.get("vendorName").replace(" ", "_").lower(),
                    "vendor_name": v.get("vendorName"),
                    "match_type": "Near Match",
                    "score": 50,
                    "reason": f"Manual match for {v.get('vendorName')} due to API failure.",
                    "adjusted_loan_amount_inr": foir_results.get(v.get("vendorName"), {}).get("adjusted_loan", loan_amount),
                    "interest_rate": v.get("criteria", {}).get("interest_rate_secured" if loan_preference == "Secured" else "interest_rate_unsecured", "12%"),
                    "loan_tenor": v.get("criteria", {}).get("loan_tenor_years", 15),
                    "processing_fee": v.get("criteria", {}).get("processing_fee", "1%"),
                    "moratorium_period": v.get("criteria", {}).get("moratorium_period", "Course duration + 6 months"),
                    "repayment_options": v.get("criteria", {}).get("repayment_options", ["SI", "EMI"]),
                    "foir_suggestion": foir_results.get(v.get("vendorName"), {}).get("message", "Loan adjusted based on profile")
                } for v in valid_vendors
            ]
            logger.info("### Step 3: Weightage-Based Ranking")
            for match in manual_matches:
                logger.info(f"{match['vendor_name']}:\n"
                            f"  - Score: {match['score']}\n"
                            f"  - Reason: {match['reason']}")
            logger.info("### Final Output")
            logger.info(json.dumps({"matches": manual_matches, "summary_text": f"Manual matching completed due to API error: {str(e)}", "fallback": no_university_vendors}, indent=2))
            logger.info(f"Final response: {len(manual_matches)} matches, fallback={no_university_vendors}")
            return manual_matches, f"Manual matching completed due to API error: {str(e)}"

def generate_document_list(student_profile: Dict) -> Optional[str]:
    """Generate a tailored document list using the OpenAI GPT-4 API with deduplication."""
    student_id = student_profile.get("student_id", "?")
    logger.info(f"Generating document list for student {student_id}")
    
    co_applicant_details = student_profile.get("co_applicant_details", {})
    if student_profile.get("loan_details", {}).get("co_applicant_available") == "Yes" and not co_applicant_details:
        logger.warning("Co-applicant details missing despite co_applicant_available: Yes")
        co_applicant_details = {
            "co_applicant_occupation": "Salaried",
            "co_applicant_relation": student_profile.get("loan_details", {}).get("co_applicant_relation", "Unknown")
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
        "Loan Type": "Secured" if student_profile.get("loan_details", {}).get("collateral_available") == "Yes" else "Student Fees",
        "Collateral Type": student_profile.get("loan_details", {}).get("collateral_type", ""),
        "Co-Applicant Available": student_profile.get("loan_details", {}).get("co_applicant_available") == "Yes",
        "Co-Applicant Occupation": co_applicant_details.get("co_applicant_occupation", ""),
        "Highest Education": student_profile.get("education_details", {}).get("highest_education_level", ""),
        "Admission Status": student_profile.get("education_details", {}).get("admission_status", 
                                    student_profile.get("education_details", {}).get("university_admission_status", "")),
        "English Test Type": student_profile.get("education_details", {}).get("english_test", {}).get("type", ""),
        "Standardized Test Type": student_profile.get("education_details", {}).get("standardized_test", {}).get("type", "")
    }
    profile_str = json.dumps(profile_summary, ensure_ascii=False)
    logger.info(f"Profile summary for document generation: {profile_str}")

    base_docs = {
        "Student Fees": {
            "Student Documents (PDF)": [
                "Photograph", "Aadhaar Card", "PAN Card", "Passport", "Offer Letter",
                "10th/12th Marksheet and Passing Certificate",
                "Degree Marksheet and Certificate (if applicable)",
                "Scorecard (IELTS, GRE, etc., if applicable)", "Student Email ID and Phone Number",
                "Bank Statements (Last 6 Months)"
            ],
            "Co-Applicant Documents (Salaried, PDF)": [
                "Photograph", "PAN Card", "Aadhaar Card", "Last 3 Months Salary Slips",
                "Last 6 Months Bank Statement", "Last 2 Years Form 16",
                "Utility Bill (e.g., Electricity Bill)", "Rent Agreement (if applicable)",
                "Co-Applicant Phone Number and Email ID"
            ],
            "Co-Applicant Documents (Self-Employed, PDF)": [
                "Photograph", "PAN Card", "Aadhaar Card",
                "GST 3B Last 1 Year and GST Certificate (Merged PDF)",
                "ITR of Last 2 Years with Computation Page",
                "Current Account Statement (Last 6 Months)",
                "Savings Account Statement (Last 6 Months)",
                "Audit Report of Last 2 Years", "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID"
            ],
            "Co-Applicant Documents (Farmer, PDF)": [
                "Photograph", "PAN Card", "Aadhaar Card", "Land Ownership Documents",
                "Last 6 Months Bank Statement", "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID"
            ],
            "Co-Applicant Documents (Unemployed, PDF)": [
                "Photograph", "PAN Card", "Aadhaar Card",
                "Last 6 Months Bank Statement (if applicable)", "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID"
            ],
            "Co-Applicant Documents (Other, PDF)": [
                "Photograph", "PAN Card", "Aadhaar Card",
                "Last 6 Months Bank Statement (if applicable)", "Utility Bill (e.g., Electricity Bill)",
                "Co-Applicant Phone Number and Email ID"
            ]
        },
        "Secured": {
            "Property Documents (Residential or Commercial)": [
                "Complete Registered Agreement", "Index 2", "Title Deed", "Sale Deed",
                "Sanctioned Plan (Blueprint)", "Non-Agricultural Order"
            ],
            "Property Owners": ["PAN Card", "Aadhaar Card"]
        }
    }
    base_docs_str = json.dumps(base_docs, ensure_ascii=False)
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
            chat_response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Document list generator."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            raw_content = chat_response.choices[0].message.content.strip()
            logger.info(f"Raw GPT-4 response for document list: {raw_content}")
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
            logger.info(f"Deduplicated document list: {json.dumps(deduplicated_docs, ensure_ascii=False)}")
            
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
            logger.error(f"Attempt {attempt + 1}/{max_retries} failed: GPT-4 API call failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
                continue
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