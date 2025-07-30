# backend/app/utils/auth.py
# Authentication utilities for JWT token handling and OTP

import os
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import pymongo
from app.models.user import TokenData, UserResponse
from app.services.email_service import send_verification_email, generate_otp, send_otp_email

logger = logging.getLogger(__name__)

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
OTP_EXPIRE_MINUTES = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))  # 10 minutes

# Password hashing (kept for backward compatibility)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer for token extraction
security = HTTPBearer()

def get_database_connection():
    """Get database connection with error handling."""
    try:
        client = pymongo.MongoClient(os.getenv("MONGO_URI"))
        db = client["FA_bots"]
        return db
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB in auth module: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection failed"
        )

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)

def generate_verification_token() -> str:
    """Generate a secure verification token."""
    return secrets.token_urlsafe(32)

def generate_and_store_otp(email: str, purpose: str = "login") -> bool:
    """Generate OTP and store it in database with expiration."""
    try:
        db = get_database_connection()
        otp = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES)
        
        # Store or update OTP in database
        db.otps.update_one(
            {"email": email, "purpose": purpose},
            {
                "$set": {
                    "otp": otp,
                    "expires_at": expires_at,
                    "created_at": datetime.utcnow(),
                    "is_used": False
                }
            },
            upsert=True
        )
        
        # Send OTP via email
        success = send_otp_email(email, otp, purpose)
        if success:
            logger.info(f"OTP generated and sent for {email} - purpose: {purpose}")
            return True
        else:
            # Clean up OTP if email failed
            db.otps.delete_one({"email": email, "purpose": purpose})
            return False
    except Exception as e:
        logger.error(f"Error generating OTP for {email}: {e}")
        return False

def verify_otp(email: str, otp: str, purpose: str = "login") -> bool:
    """Verify OTP and mark it as used."""
    try:
        db = get_database_connection()
        
        # Find valid OTP
        otp_doc = db.otps.find_one({
            "email": email,
            "purpose": purpose,
            "otp": otp,
            "expires_at": {"$gt": datetime.utcnow()},
            "is_used": False
        })
        
        if not otp_doc:
            logger.warning(f"Invalid or expired OTP for {email}")
            return False
        
        # Mark OTP as used
        db.otps.update_one(
            {"_id": otp_doc["_id"]},
            {"$set": {"is_used": True, "used_at": datetime.utcnow()}}
        )
        
        logger.info(f"OTP verified successfully for {email}")
        return True
    except Exception as e:
        logger.error(f"Error verifying OTP for {email}: {e}")
        return False

def cleanup_expired_otps():
    """Clean up expired OTPs from database."""
    try:
        db = get_database_connection()
        result = db.otps.delete_many({
            "expires_at": {"$lt": datetime.utcnow()}
        })
        logger.info(f"Cleaned up {result.deleted_count} expired OTPs")
    except Exception as e:
        logger.error(f"Error cleaning up OTPs: {e}")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_data = TokenData(email=email)
        return token_data
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_user_by_email(email: str) -> Optional[dict]:
    """Get user from database by email."""
    try:
        db = get_database_connection()
        user = db.users.find_one({"email": email})
        return user
    except Exception as e:
        logger.error(f"Error fetching user by email: {e}")
        return None

def create_user_in_db(user_data: dict) -> str:
    """Create a new user in the database."""
    try:
        db = get_database_connection()
        user_data["created_at"] = datetime.utcnow()
        user_data["updated_at"] = datetime.utcnow()
        user_data["is_active"] = True
        user_data["is_verified"] = False  # Users start as unverified
        
        # Generate a unique ID for the user (using email as unique identifier)
        user_data["id"] = user_data["email"]
        
        # Check if user with this email already exists
        existing_user = db.users.find_one({"email": user_data["email"]})
        if existing_user:
            logger.warning(f"Attempted to create duplicate user with email: {user_data['email']}")
            raise ValueError("User with this email already exists")
        
        result = db.users.insert_one(user_data)
        logger.info(f"Created new user with ID: {result.inserted_id}")
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Error creating user in database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )

def send_verification_email_to_user(email: str, verification_token: str, full_name: Optional[str] = None) -> bool:
    """Send verification email to user."""
    try:
        # Create verification URL
        base_url = os.getenv("FRONTEND_URL", "http://localhost:8080")
        verification_url = f"{base_url}/verify-email?token={verification_token}"
        
        # Email content
        subject = "Verify Your Email - LoanWise Buddy"
        
        # Personalized greeting
        greeting = f"Hello {full_name}!" if full_name else "Hello!"
        
        body = f"""
{greeting}

Thank you for signing up with LoanWise Buddy! Please verify your email address by clicking the link below:

{verification_url}

This link will expire in {VERIFICATION_TOKEN_EXPIRE_HOURS} hours.

If you didn't create an account with us, please ignore this email.

Best regards,
The LoanWise Buddy Team
        """
        
        return send_verification_email(email, subject, body.strip())
    except Exception as e:
        logger.error(f"Error sending verification email: {e}")
        return False

def verify_email_token(token: str) -> Optional[str]:
    """Verify email verification token and return user email if valid."""
    try:
        db = get_database_connection()
        
        # Find user with this verification token
        user = db.users.find_one({
            "verification_token": token,
            "verification_token_expires": {"$gt": datetime.utcnow()},
            "is_verified": False
        })
        
        if not user:
            return None
        
        # Update user as verified
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "is_verified": True,
                    "verification_token": None,
                    "verification_token_expires": None,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Email verified for user: {user['email']}")
        return user["email"]
    except Exception as e:
        logger.error(f"Error verifying email token: {e}")
        return None

def resend_verification_email(email: str) -> bool:
    """Resend verification email to user."""
    try:
        db = get_database_connection()
        user = db.users.find_one({"email": email, "is_verified": False})
        
        if not user:
            return False
        
        # Generate new verification token
        new_token = generate_verification_token()
        expires_at = datetime.utcnow() + timedelta(hours=VERIFICATION_TOKEN_EXPIRE_HOURS)
        
        # Update user with new token
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "verification_token": new_token,
                    "verification_token_expires": expires_at,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Send new verification email
        return send_verification_email_to_user(
            email, 
            new_token, 
            user.get("full_name")
        )
    except Exception as e:
        logger.error(f"Error resending verification email: {e}")
        return False

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserResponse:
    """Get current authenticated user."""
    token = credentials.credentials
    token_data = verify_token(token)
    
    user = get_user_by_email(token_data.email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user.get("full_name"),
        mobile_number=user.get("mobile_number"),
        is_active=user.get("is_active", True),
        is_verified=user.get("is_verified", False),
        created_at=user["created_at"],
        updated_at=user["updated_at"]
    )

def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Authenticate user with email and password (legacy)."""
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["password"]):
        return None
    return user

def authenticate_user_with_otp(email: str, otp: str) -> Optional[dict]:
    """Authenticate user with email and OTP."""
    # First verify the OTP
    if not verify_otp(email, otp, "login"):
        return None
    
    # Get user from database
    user = get_user_by_email(email)
    if not user:
        return None
    
    return user
