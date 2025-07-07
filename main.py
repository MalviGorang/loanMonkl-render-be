# backend/main.py
# Entry point for the FastAPI application

import logging
import pymongo
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
)

# Add CORS middleware for frontend communication
# Add CORS middleware for frontend communication
origins = [
    "http://localhost:5174",
    "http://localhost:3000",
    "https://loan-monk-ai-fe-eb1r.vercel.app",
    "http://fa-loanmaon-dev-fe-1286572314.ap-south-1.elb.amazonaws.com",
    "https://fa-loanmaon-dev-fe-1286572314.ap-south-1.elb.amazonaws.com",
    "http://dev-be-fa-loanmonk-1035406255.ap-south-1.elb.amazonaws.com",
    "https://dev-be-fa-loanmonk-1035406255.ap-south-1.elb.amazonaws.com",
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
