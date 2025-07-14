# backend/app/routes/auth.py
# Authentication routes for login, signup, and token management

import logging
from datetime import timedelta, datetime
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.user import UserCreate, UserLogin, Token, UserResponse
from app.utils.auth import (
    authenticate_user, 
    create_access_token, 
    get_password_hash, 
    get_user_by_email, 
    create_user_in_db,
    get_current_user,
    send_verification_email_to_user,
    verify_email_token,
    resend_verification_email,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from app.utils.validators import validate_email, validate_phone

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/signup", response_model=dict)
async def signup(user: UserCreate):
    """Register a new user and send verification email."""
    logger.info(f"Signup attempt for email: {user.email}")
    
    try:
        # Validate email format
        if not validate_email(user.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )
        
        # Validate mobile number if provided
        if user.mobile_number and not validate_phone(user.mobile_number):
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
        
        # Hash password and create user
        hashed_password = get_password_hash(user.password)
        user_data = {
            "email": user.email,
            "password": hashed_password,
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
        
        # Get created user to get verification token
        created_user = get_user_by_email(user.email)
        if not created_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created user"
            )
        
        # Send verification email
        verification_sent = send_verification_email_to_user(
            user.email, 
            created_user["verification_token"], 
            user.full_name or None
        )
        
        if not verification_sent:
            logger.warning(f"Failed to send verification email to {user.email}")
            # For testing: auto-verify the user if email fails
            try:
                from app.utils.auth import get_database_connection
                db = get_database_connection()
                db.users.update_one(
                    {"email": user.email},
                    {
                        "$set": {
                            "is_verified": True,
                            "verification_token": None,
                            "verification_token_expires": None,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                logger.info(f"Auto-verified user for testing: {user.email}")
                verification_sent = True
            except Exception as e:
                logger.error(f"Failed to auto-verify user: {e}")
        
        logger.info(f"User created successfully: {user.email}")
        return {
            "message": "User created successfully. Please check your email to verify your account.",
            "email": user.email,
            "verification_sent": verification_sent
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during signup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )

@router.post("/login", response_model=Token)
async def login(user: UserLogin):
    """Authenticate user and return access token."""
    logger.info(f"Login attempt for email: {user.email}")
    
    try:
        # Authenticate user
        authenticated_user = authenticate_user(user.email, user.password)
        if not authenticated_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
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
            verification_token=authenticated_user.get("verification_token"),
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

class VerifyEmailRequest(BaseModel):
    token: str

class ResendVerificationRequest(BaseModel):
    email: str

@router.post("/verify-email")
async def verify_email(request: VerifyEmailRequest):
    """Verify user email with verification token."""
    logger.info(f"Email verification attempt with token: {request.token[:10]}...")
    
    try:
        verified_email = verify_email_token(request.token)
        if not verified_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token"
            )
        
        logger.info(f"Email verified successfully: {verified_email}")
        return {
            "message": "Email verified successfully. You can now log in.",
            "email": verified_email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during email verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email verification failed"
        )

@router.post("/resend-verification")
async def resend_verification_email_endpoint(request: ResendVerificationRequest):
    """Resend verification email to user."""
    logger.info(f"Resend verification email request for: {request.email}")
    
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
        
        # Resend verification email
        success = resend_verification_email(request.email)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification email"
            )
        
        logger.info(f"Verification email resent to: {request.email}")
        return {
            "message": "Verification email sent successfully",
            "email": request.email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending verification email: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification email"
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
