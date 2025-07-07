# backend/app/api/routes.py
# API routes for student, vendor, and document operations

import logging
from fastapi import APIRouter, HTTPException
from app.models.student import Student
from app.services.llm_service import generate_document_list, get_llm_vendor_matches
from app.services.s3_service import generate_presigned_url
from app.services.pincode_service import get_location_from_pincode
from app.utils.validators import (
    validate_email,
    validate_phone,
    validate_pincode,
    validate_cibil_score,
    validate_pan,
    validate_aadhaar,
)
from typing import Dict, List, Optional
import pymongo
from datetime import datetime
import os
import json

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

# MongoDB client
try:
    client = pymongo.MongoClient(os.getenv("MONGO_URI"))
    db = client["FA_bots"]
    logger.info("Connected to MongoDB")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    raise HTTPException(status_code=500, detail="Database connection failed")


@router.post("/students")
async def create_student(student: Student):
    """Create or update a student profile."""
    logger.info(f"Received student profile data")
    try:
        student_dict = student.dict(exclude_unset=True)

        # Ensure required fields exist
        if "education_details" not in student_dict:
            student_dict["education_details"] = {}
        if "loan_details" not in student_dict:
            student_dict["loan_details"] = {}
        if "co_applicant_details" not in student_dict:
            student_dict["co_applicant_details"] = {}

        # Validate collateral pincode if collateral is available
        if student_dict.get("loan_details", {}).get("collateral_available") == "Yes":
            collateral_pincode = student_dict["loan_details"].get(
                "collateral_location_pincode"
            )
            if collateral_pincode and not validate_pincode(collateral_pincode):
                raise HTTPException(
                    status_code=400, detail="Invalid collateral pincode format"
                )

        if student.email and not validate_email(student.email):
            logger.warning(f"Invalid email format: {student.email}")
            raise HTTPException(status_code=400, detail="Invalid email format")
        if student.mobile_number and not validate_phone(student.mobile_number):
            logger.warning(f"Invalid phone format: {student.mobile_number}")
            raise HTTPException(status_code=400, detail="Invalid phone format")
        if not student.mobile_number:
            logger.warning("Mobile number is required")
            raise HTTPException(status_code=400, detail="Mobile number is required")
        if student.current_location_pincode and not validate_pincode(
            student.current_location_pincode
        ):
            logger.warning(
                f"Invalid pincode format: {student.current_location_pincode}"
            )
            raise HTTPException(status_code=400, detail="Invalid pincode format")
        if student.loan_details:
            if student.loan_details.cibil_score and not validate_cibil_score(
                student.loan_details.cibil_score
            ):
                logger.warning(
                    f"Invalid CIBIL score: {student.loan_details.cibil_score}"
                )
                raise HTTPException(status_code=400, detail="Invalid CIBIL score")
            if student.loan_details.pan and not validate_pan(student.loan_details.pan):
                logger.warning(f"Invalid PAN format: {student.loan_details.pan}")
                raise HTTPException(status_code=400, detail="Invalid PAN format")
            if student.loan_details.aadhaar and not validate_aadhaar(
                student.loan_details.aadhaar
            ):
                logger.warning(
                    f"Invalid Aadhaar format: {student.loan_details.aadhaar}"
                )
                raise HTTPException(status_code=400, detail="Invalid Aadhaar format")
            if student.loan_details.co_applicant_pan and not validate_pan(
                student.loan_details.co_applicant_pan
            ):
                logger.warning(
                    f"Invalid co-applicant PAN format: {student.loan_details.co_applicant_pan}"
                )
                raise HTTPException(
                    status_code=400, detail="Invalid co-applicant PAN format"
                )
            if student.loan_details.co_applicant_aadhaar and not validate_aadhaar(
                student.loan_details.co_applicant_aadhaar
            ):
                logger.warning(
                    f"Invalid co-applicant Aadhaar format: {student.loan_details.co_applicant_aadhaar}"
                )
                raise HTTPException(
                    status_code=400, detail="Invalid co-applicant Aadhaar format"
                )

        student_dict = student.dict(exclude_unset=True)
        # Map mobile_number to mobile
        if "mobile_number" in student_dict:
            student_dict["mobile"] = student_dict.pop("mobile_number")
        student_dict["created_at"] = datetime.utcnow()
        student_dict["updated_at"] = datetime.utcnow()
        if student.current_location_pincode:
            location = get_location_from_pincode(student.current_location_pincode)
            if location:
                student_dict["current_location_city"] = location["city"]
                student_dict["current_location_state"] = location["state"]
                logger.info(
                    f"Pincode {student.current_location_pincode} resolved to city: {location['city']}, state: {location['state']}"
                )
            else:
                logger.warning(
                    f"Pincode lookup failed for {student.current_location_pincode}"
                )
        if "student_id" in student_dict:
            db.students.update_one(
                {"student_id": student_dict["student_id"]},
                {"$set": student_dict},
                upsert=True,
            )
            logger.info(
                f"Updated student profile with ID: {student_dict['student_id']}"
            )
        else:
            logger.info(f"Inserting student document: {student_dict}")
            result = db.students.insert_one(student_dict)
            student_dict["student_id"] = str(result.inserted_id)
            logger.info(
                f"Created new student profile with ID: {student_dict['student_id']}"
            )
        return {"student_id": student_dict["student_id"]}
    except Exception as e:
        logger.error(f"Error creating student profile: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/countries")
async def get_countries():
    """Fetch all available countries."""
    logger.info("Received GET /api/countries")
    try:
        countries = list(db.universities.distinct("universityCountry"))
        logger.info(f"Found {len(countries)} countries")
        return countries
    except Exception as e:
        logger.error(f"Error fetching countries: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/universities")
async def get_universities(country: Optional[str] = None, search: Optional[str] = None):
    """Fetch universities, optionally filtered by country and search term."""
    logger.info(
        f"Received GET /api/universities with country: {country}, search: {search}"
    )
    try:
        query = {}
        if country:
            query["universityCountry"] = country
        if search:
            query["name"] = {"$regex": search, "$options": "i"}
        universities = list(
            db.universities.find(query, {"name": 1, "vendors": 1, "_id": 0})
        )
        logger.info(f"Found {len(universities)} universities")
        return universities
    except Exception as e:
        logger.error(f"Error fetching universities: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/courses")
async def get_courses(course_type: Optional[str] = None, degree: Optional[str] = None):
    """Fetch courses filtered by course type and degree."""
    logger.info(
        f"Received GET /api/courses with course_type: {course_type}, degree: {degree}"
    )
    try:
        query = {}

        if course_type:
            study_area_map = {
                "STEM": "Stem",
                "NON-STEM": "NonStem",
                "MANAGEMENT": "Management",
                "OTHER": "Other",
            }
            query["studyArea"] = study_area_map.get(course_type.upper(), "Other")

        if degree:
            query["degreeLevel"] = degree

        logger.debug(f"MongoDB query: {query}")
        courses = list(db.courses.find(query, {"specialization": 1, "_id": 0}))
        logger.info(f"Found {len(courses)} courses for query: {query}")

        # Filter out documents missing specialization
        course_names = [
            course["specialization"] for course in courses if "specialization" in course
        ]
        if not course_names:
            logger.warning("No courses found with specialization field")
            return []
        return sorted(course_names)

    except Exception as e:
        logger.error(f"Error fetching courses: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pincode/{pincode}")
async def lookup_pincode(pincode: str):
    """Fetch city and state for a given pincode."""
    logger.info(f"Received GET /api/pincode/{pincode}")
    try:
        if not validate_pincode(pincode):
            logger.warning(f"Invalid pincode format: {pincode}")
            raise HTTPException(status_code=400, detail="Invalid pincode format")
        location = get_location_from_pincode(pincode)
        if not location:
            logger.warning(f"Pincode not found: {pincode}")
            raise HTTPException(status_code=404, detail="Pincode not found")
        logger.info(f"Pincode {pincode} resolved to: {location}")
        return location
    except Exception as e:
        logger.error(f"Error looking up pincode: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vendors/match")
async def match_vendors(student: Student):
    """Match student profile with vendors."""
    logger.info(
        f"Received POST /api/vendors/match with payload: {json.dumps(student.dict(exclude_unset=True), default=str)}"
    )
    try:
        matches, summary = get_llm_vendor_matches(student.dict(exclude_unset=True))
        logger.info(f"Vendor matching completed: {summary}")

        # Ensure matches is always an array
        if not isinstance(matches, list):
            matches = []

        return {"matches": matches, "summary": summary}
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error matching vendors: {error_message}")
        # Return a safe error response
        return {"matches": [], "summary": f"Failed to match vendors: {error_message}"}


@router.post("/documents/generate")
async def generate_documents(student: Student):
    """Generate a tailored document list for the student."""
    logger.info(
        f"Received POST /api/documents/generate with payload: {json.dumps(student.dict(exclude_unset=True), default=str)}"
    )
    try:
        doc_list = generate_document_list(student.dict(exclude_unset=True))

        # Ensure doc_list is a string, then split into array
        if not doc_list:
            doc_list = []
        elif isinstance(doc_list, str):
            doc_list = [line.strip() for line in doc_list.split("\n") if line.strip()]

        logger.info("Document list generated successfully")

        # Return properly formatted JSON response
        logger.info(f"Returning document list with {len(doc_list)} items")
        return {"document_list": doc_list}
    except Exception as e:
        logger.error(f"Error generating documents: {str(e)}")
        return {"document_list": []}  # Return empty array instead of string


@router.post("/documents/upload-url")
async def get_upload_url(student_id: str, document_type: str, file_name: str):
    """Generate a pre-signed URL for document upload."""
    logger.info(
        f"Received POST /api/documents/upload-url with student_id: {student_id}, document_type: {document_type}, file_name: {file_name}"
    )
    try:
        url = generate_presigned_url(student_id, document_type, file_name)
        if not url:
            logger.error("Failed to generate pre-signed URL")
            raise HTTPException(status_code=500, detail="Failed to generate upload URL")
        logger.info(f"Generated pre-signed URL for {file_name}")
        return {"url": url}
    except Exception as e:
        logger.error(f"Error generating upload URL: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/courses/{course_type}")
async def get_courses(course_type: str):
    """Get list of courses based on course type."""
    logger.info(f"Received GET /api/courses/{course_type}")
    try:
        from app.services.course_service import get_courses_by_type

        courses = get_courses_by_type(course_type)
        return {"courses": courses}
    except Exception as e:
        logger.error(f"Error fetching courses: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch courses")
