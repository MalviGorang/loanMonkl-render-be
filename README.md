Loan Assistance Tool Backend
Summary
This is the backend for an AI-driven student loan assistance tool, built with FastAPI, MongoDB, and AWS S3. It handles student profile collection, vendor matching using a Large Language Model (LLM) via the Simplismart API, document generation, and secure document uploads to S3. The backend supports a modal-based question flow with conditional logic, input validation, and dynamic vendor lookup for universities.
Folder Structure
backend/
├── app/
│   ├── api/
│   │   └── routes.py         # API endpoints for student, vendor, document operations
│   ├── models/
│   │   └── student.py        # Pydantic model for student profile
│   ├── services/
│   │   ├── llm_service.py    # LLM integration for vendor matching and document generation
│   │   ├── s3_service.py     # AWS S3 integration for document uploads
│   │   ├── pincode_service.py # Pincode lookup service
│   │   └── vendor_service.py # Vendor matching logic with FOIR calculations
│   ├── utils/
│   │   ├── constants.py      # Question details and currency options
│   │   ├── validators.py     # Input validation functions
│   │   └── auth.py           # JWT authentication utilities
├── tests/
│   └── test_validators.py    # Unit tests for validators
├── main.py                   # FastAPI entry point
├── requirements.txt          # Python dependencies
└── .env                      # Environment variables

Installation Guide

Prerequisites:

Python 3.9+
MongoDB (local or cloud, e.g., MongoDB Atlas)
AWS account with S3 bucket (loan-documents-bucket)
Simplismart API key for LLM integration


Clone Repository (if applicable):
git clone <repository-url>
cd backend


Set Up Virtual Environment:
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate


Install Dependencies:
pip install -r requirements.txt


Configure Environment Variables:Create a .env file in the backend/ directory:
SIMPLISMART_API_KEY=your_api_key
SIMPLISMART_BASE_URL=https://http.llm.proxy.prod.s9t.link
SIMPLISMART_ID_HEADER=your_id_header
MONGO_URI=mongodb://localhost:27017/FA_bots
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
S3_BUCKET_NAME=loan-documents-bucket
JWT_SECRET_KEY=your-secret-key


Set Up MongoDB:

Create a database named FA_bots.
Create collections: students, vendors, universities, pincode, courses.
Import dummy data (see below) into vendors, universities, pincode, and courses.


Run the Application:
uvicorn main:app --reload

The API will be available at http://localhost:8000.


Dummy Data for Testing
To test the API in Postman, populate the MongoDB collections with the following dummy data. Use a MongoDB client (e.g., MongoDB Compass) or command line to insert these documents.
vendors Collection
{
  "vendorName": "Example Bank",
  "vendorType": "PSU",
  "active": true,
  "criteria": {
    "loan_options": ["Secured"],
    "max_secured_loan_inr": 25000000,
    "max_unsecured_loan_inr": null,
    "min_loan_inr": null,
    "interest_rate_secured": "9.75%",
    "interest_rate_unsecured": null,
    "processing_fee": "0.5%",
    "loan_tenor_years": 15,
    "moratorium_period": "Course duration + 1 year",
    "repayment_options": ["PSI", "SI", "EMI"],
    "prepayment_penalty": "None",
    "margin_money_percentage": 15,
    "supported_countries": ["Canada", "USA"],
    "supported_degrees": ["Masters", "Bachelors"],
    "supported_courses": ["Stem", "Management"],
    "requires_admission": false,
    "min_academic_score_percentage": 60,
    "max_educational_backlogs": 15,
    "min_ielts_score": 6,
    "max_student_age": 30,
    "requires_co_applicant": true,
    "supported_co_applicant_relations": ["Father", "Mother"],
    "basic_income_norms": {
      "salaried_inr_monthly": 20000
    },
    "own_house_required": false,
    "requires_collateral": true,
    "supported_collateral_types": ["Property", "Fixed Deposit"],
    "geographical_restrictions": [],
    "interest_subsidy_eligibility": "CSIS for income < ₹4.5L",
    "cibil_score_requirement": "None",
    "Foir": {
      "salaried": 75
    }
  }
}

universities Collection
{
  "name": "University of Toronto",
  "universityCountry": "Canada",
  "rank": 21,
  "vendors": ["Example Bank"]
}

pincode Collection
{
  "pincode": "560066",
  "city": "Bangalore",
  "state": "Karnataka",
  "region": "South India"
}

courses Collection
{
  "course_name": "Computer Science",
  "university_name": "University of Toronto",
  "degree_level": "Masters",
  "course_category": "Stem"
}

Postman Testing

Health Check:

GET http://localhost:8000/
Response: {"message": "Loan Assistance Tool API is running"}


Create Student Profile:

POST http://localhost:8000/api/students
Headers: Authorization: Bearer your-jwt-token
Body (JSON):{
  "name": "John Doe",
  "mobile_number": "+919876543210",
  "email": "john.doe@example.com",
  "date_of_birth": "2000-01-01",
  "current_location_pincode": "560066",
  "education_details": {
    "marks_10th": { "format": "Percentage", "value": 85 },
    "marks_12th": { "format": "Percentage", "value": 90 },
    "highest_education_level": "Bachelors",
    "academic_score": { "format": "Percentage", "value": 75 },
    "educational_backlogs": 0,
    "education_gap": "No",
    "current_profession": "Student",
    "university_admission_status": "Admission letter received",
    "study_destination_country": ["Canada"],
    "university_name": ["University of Toronto"],
    "intended_degree": "Masters",
    "specific_course_name": "Computer Science",
    "target_intake": "Fall",
    "course_duration": { "years": 2, "months": 0 },
    "english_test": { "type": "IELTS", "score": 7.5 },
    "standardized_test": { "type": "None" }
  },
  "loan_details": {
    "loan_amount_requested": { "amount": 1500000, "currency": "INR" },
    "collateral_available": "Yes",
    "collateral_type": "Property",
    "collateral_value_amount": { "amount": 5000000, "currency": "INR" },
    "collateral_location_pincode": "560066",
    "collateral_existing_loan": "No",
    "co_applicant_available": "Yes",
    "cibil_score": "720",
    "pan": "ABCDE1234F",
    "aadhaar": "123456789012"
  },
  "co_applicant_details": {
    "co_applicant_relation": "Father",
    "co_applicant_occupation": "Salaried",
    "co_applicant_income_amount": { "amount": 800000, "currency": "INR" },
    "co_applicant_existing_loan": "No",
    "co_applicant_pan": "XYZAB5678C",
    "co_applicant_aadhaar": "987654321098"
  }
}


Response: {"student_id": "<generated_id>"}


Fetch Universities:

GET http://localhost:8000/api/universities?country=Canada
Response: [{"name": "University of Toronto", "vendors": ["Example Bank"]}]


Match Vendors:

POST http://localhost:8000/api/vendors/match
Headers: Authorization: Bearer your-jwt-token
Body: Use the same student profile as above.
Response: (Example){
  "matches": [
    {
      "vendor_id": "<id>",
      "vendor_name": "Example Bank",
      "match_type": "Best Match",
      "score": 80,
      "reason": "Loan amount within FOIR limit.",
      "adjusted_loan_amount_inr": 1500000,
      "interest_rate": "9.75%",
      "loan_tenor": 15,
      "processing_fee": "0.5%",
      "moratorium_period": "Course duration + 1 year",
      "repayment_options": ["PSI", "SI", "EMI"],
      "foir_suggestion": "Loan amount within FOIR limit."
    }
  ],
  "summary": "Found 1 matching vendors."
}




Generate Document List:

POST http://localhost:8000/api/documents/generate
Headers: Authorization: Bearer your-jwt-token
Body: Use the same student profile.
Response: (Example){
  "document_list": "Required Documents for Education Loan - Secured\n\nStudent Documents (PDF):\n1. Photo\n2. Aadhaar Card\n3. PAN Card\n4. Passport\n5. Offer Letter\n6. 10th/12th Marksheet and Passing Certificate\n7. Degree Marksheet and Degree Certificate\n8. Scorecard (IELTS)\n9. Student Email ID and Phone Number\n10. Bank Statements\n\nCo-Applicant Documents (Salaried, PDF):\n1. Photo\n2. PAN Card\n3. Aadhaar Card\n4. Last 3 Months Salary Slip\n5. Last 6 Months Bank Statement\n6. Last 2 Years Form 16 (A/B) Part\n7. House Light Bill\n8. Rent Agreement (if house is rented)\n9. Phone Number and Email ID of Co-Applicant\n\nProperty Documents (Property, PDF):\n1. Complete Register Agreement\n2. Index 2\n3. Plan Copy\n4. Sale Deed\n5. Sanction Plan (Blueprint)\n6. NA Order"
}




Get S3 Upload URL:

POST http://localhost:8000/api/documents/upload-url
Headers: Authorization: Bearer your-jwt-token
Body:{
  "student_id": "<student_id>",
  "document_type": "Photo",
  "file_name": "photo.jpg"
}


Response: {"url": "<pre-signed-url>"}



How to Use

Start the Server:

Run uvicorn main:app --reload to start the backend.
Access the API at http://localhost:8000.


Test with Postman:

Use the dummy data and endpoints above to test functionality.
Ensure JWT tokens are included in headers (implement a login system or use a static token for testing).


Interact with Frontend:

The backend serves the frontend at http://localhost:5173.
Ensure the frontend’s .env has VITE_API_URL=http://localhost:8000.


Key Features:

Student Profile: Collects data via API with conditional questions.
Vendor Matching: Uses LLM to match vendors based on profile and FOIR calculations.
Document Generation: Generates tailored document lists.
S3 Uploads: Supports secure document uploads.
Pincode Lookup: Fetches city and state from pincodes.



Notes

Replace placeholder JWT tokens with a proper authentication system.
Update exchange rates in vendor_service.py for accurate FOIR calculations.
Ensure MongoDB collections are populated with sufficient data for testing.

