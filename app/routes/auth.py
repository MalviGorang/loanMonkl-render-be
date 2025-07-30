# backend/app/routes/auth.py
# Authentication routes for OTP-based login, signup, and token management

import logging
from datetime import timedelta, datetime
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.user import UserCreate, UserLogin, Token, UserResponse, OTPRequest, OTPVerification
from app.utils.auth import (
    authenticate_user_with_otp, 
    create_access_token, 
    get_user_by_email, 
    create_user_in_db,
    get_current_user,
    generate_and_store_otp,
    verify_otp,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.utils.validators import validate_email, validate_phone

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/signup", response_model=dict)
async def signup(user: UserCreate):
    """Register a new user and send OTP for email verification."""
    logger.info(f"Signup attempt for email: {user.email}")
    
    try:
        # Validate email format
        if not validate_email(user.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        
        # Validate mobile number
        if not validate_phone(user.mobile_number):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid mobile number format"
            )
        
        # Check if user already exists
        existing_user = get_user_by_email(user.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create user data (no password required)
        user_data = {
            "email": user.email,
            "full_name": user.full_name,
            "mobile_number": user.mobile_number
        }
        
        try:
            user_id = create_user_in_db(user_data)
        except ValueError as e:
            # This catches the error if the user already exists
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        except Exception as e:
            logger.error(f"Error creating user in database: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )
        
        # Generate and send OTP for email verification
        otp_sent = generate_and_store_otp(user.email, "registration")
        
        if not otp_sent:
            logger.warning(f"Failed to send OTP to {user.email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification OTP"
            )
        
        logger.info(f"User created successfully: {user.email}")
        return {
            "message": "User created successfully. Please check your email for OTP to verify your account.",
            "email": user.email,
            "otp_sent": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during signup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )

@router.post("/verify-registration-otp")
async def verify_registration_otp(request: OTPVerification):
    """Verify OTP during registration and activate user account."""
    logger.info(f"Registration OTP verification attempt for email: {request.email}")
    
    try:
        # Validate email format
        if not validate_email(request.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        
        # Check if user exists and is not verified
        user = get_user_by_email(request.email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if user.get("is_verified", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already verified"
            )
        
        # Verify OTP
        if not verify_otp(request.email, request.otp, "registration"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired OTP"
            )
        
        # Mark user as verified
        from app.utils.auth import get_database_connection
        db = get_database_connection()
        db.users.update_one(
            {"email": request.email},
            {
                "$set": {
                    "is_verified": True,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"User registration verified successfully: {request.email}")
        return {
            "message": "Email verified successfully. You can now log in.",
            "email": request.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during registration OTP verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OTP verification failed"
        )

@router.post("/request-login-otp")
async def request_login_otp(request: OTPRequest):
    """Request OTP for login."""
    logger.info(f"Login OTP request for email: {request.email}")
    
    try:
        # Validate email format
        if not validate_email(request.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        
        # Check if user exists and is verified
        user = get_user_by_email(request.email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if not user.get("is_verified", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please verify your email address first"
            )
        
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled"
            )
        
        # Generate and send OTP
        otp_sent = generate_and_store_otp(request.email, "login")
        
        if not otp_sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send login OTP"
            )
        
        logger.info(f"Login OTP sent to: {request.email}")
        return {
            "message": "Login OTP sent successfully",
            "email": request.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting login OTP: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send login OTP"
        )
@router.post("/login", response_model=Token)
async def login(user: UserLogin):
    """Authenticate user with email and OTP."""
    logger.info(f"Login attempt for email: {user.email}")
    
    try:
        # Authenticate user with OTP
        authenticated_user = authenticate_user_with_otp(user.email, user.otp)
        if not authenticated_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or OTP",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if user is active
        if not authenticated_user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled"
            )
        
        # Check if user is verified
        if not authenticated_user.get("is_verified", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please verify your email address before logging in"
            )
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": authenticated_user["email"]}, expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=str(authenticated_user["_id"]),
            email=authenticated_user["email"],
            full_name=authenticated_user.get("full_name"),
            mobile_number=authenticated_user.get("mobile_number"),
            is_active=authenticated_user.get("is_active", True),
            is_verified=authenticated_user.get("is_verified", False),
            created_at=authenticated_user["created_at"],
            updated_at=authenticated_user["updated_at"]
        )
        
        logger.info(f"User logged in successfully: {user.email}")
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

from pydantic import BaseModel

class ResendOTPRequest(BaseModel):
    email: str
    purpose: str = "registration"  # Can be "registration" or "login"

@router.post("/resend-otp")
async def resend_otp(request: ResendOTPRequest):
    """Resend OTP to user."""
    logger.info(f"Resend OTP request for: {request.email}, purpose: {request.purpose}")
    
    try:
        # Validate email format
        if not validate_email(request.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        
        # Check if user exists
        user = get_user_by_email(request.email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # For registration OTP, user should not be verified
        if request.purpose == "registration" and user.get("is_verified", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already verified"
            )
        
        # For login OTP, user should be verified
        if request.purpose == "login" and not user.get("is_verified", False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please verify your email address first"
            )
        
        # Generate and send new OTP
        success = generate_and_store_otp(request.email, request.purpose)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP"
            )
        
        logger.info(f"OTP resent to: {request.email}")
        return {
            "message": f"{request.purpose.title()} OTP sent successfully",
            "email": request.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending OTP: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend OTP"
        )

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserResponse = Depends(get_current_user)):
    """Get current user information."""
    logger.info(f"User profile requested: {current_user.email}")
    return current_user

@router.post("/logout")
async def logout(current_user: UserResponse = Depends(get_current_user)):
    """Logout user (client-side token removal)."""
    logger.info(f"User logged out: {current_user.email}")
    return {"message": "Successfully logged out"}

@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: UserResponse = Depends(get_current_user)):
    """Refresh access token."""
    logger.info(f"Token refresh requested: {current_user.email}")
    
    try:
        # Create new access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": current_user.email}, expires_delta=access_token_expires
        )
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=current_user
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during token refresh: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )
