# backend/main.py
# Entry point for the FastAPI application

import logging
import pymongo
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from app.api.routes import router
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("backend.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Suppress pymongo debug logs
logging.getLogger("pymongo").setLevel(logging.WARNING)

# Load environment variables
load_dotenv()
logger.info("Environment variables loaded from .env")

# Validate required environment variables
required_env_vars = ["MONGO_URI"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {missing_vars}")
    raise Exception(f"Missing required environment variables: {missing_vars}")

# Validate optional but important environment variables
optional_vars = [
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "S3_BUCKET_NAME",
    "OPENAI_API_KEY",
]
missing_optional = [var for var in optional_vars if not os.getenv(var)]
if missing_optional:
    logger.warning(
        f"Missing optional environment variables (some features may not work): {missing_optional}"
    )

# Initialize MongoDB client
try:
    mongo_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
    mongo_client.server_info()  # Test connection
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    raise Exception(f"MongoDB connection failed: {str(e)}")

# Initialize FastAPI app
app = FastAPI(
    title="Loan Assistance Tool API",
    description="API for an AI-driven student loan assistance tool",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENVIRONMENT") == "development" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT") == "development" else None,
)

# Add security middleware
if os.getenv("ENVIRONMENT") == "production":
    # Add trusted host middleware for production
    allowed_hosts = (
        os.getenv("ALLOWED_HOSTS", "").split(",")
        if os.getenv("ALLOWED_HOSTS")
        else ["*"]
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


# Add security headers middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    if os.getenv("ENVIRONMENT") == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


# Add CORS middleware for frontend communication
origins = [
    "http://localhost:8080",  # Vite dev server
    "http://localhost:5174",
    "http://localhost:3000",
    "https://loan-monk-ai-fe-eb1r.vercel.app",
    "http://fa-loanmaon-dev-fe-1286572314.ap-south-1.elb.amazonaws.com",
    "https://fa-loanmaon-dev-fe-1286572314.ap-south-1.elb.amazonaws.com",
    "http://dev-be-fa-loanmonk-1035406255.ap-south-1.elb.amazonaws.com",
    "https://dev-be-fa-loanmonk-1035406255.ap-south-1.elb.amazonaws.com",
    "https://9db1bae1-6a35-4211-88c7-a2fdf134135a.lovableproject.com"
]

# Add wildcard origin in development environment
if os.getenv("ENVIRONMENT") == "development":
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=600,
)
logger.info(f"CORS middleware configured with origins: {origins}")

# Include API routes
app.include_router(router, prefix="/api")
logger.info("API routes included")


# Health check endpoint
@app.get("/")
async def root():
    """Return a basic health check message."""
    logger.info("Health check endpoint accessed")
    try:
        mongo_client.server_info()  # Verify MongoDB connection
        return {"message": "Loan Assistance Tool API is running"}
    except Exception as e:
        logger.error(f"MongoDB health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Database connection error")
