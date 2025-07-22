# Email Verification Setup Guide

This guide will help you set up the email verification system for the LoanWise Buddy application.

## Environment Variables

Create a `.env` file in the backend directory with the following variables:

```env
# Database Configuration
MONGO_URI=mongodb://localhost:27017/FA_bots

# JWT Configuration
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Email Verification Configuration
VERIFICATION_TOKEN_EXPIRE_HOURS=24
FRONTEND_URL=http://localhost:3000

# SMTP Configuration for Email Verification
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
EMAIL_SENDER=your-email@gmail.com
```

## SMTP Configuration

### Gmail Setup (Recommended for Development)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password**:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password for "Mail"
   - Use this password as `SMTP_PASS`

### Alternative SMTP Providers

- **Outlook/Hotmail**: `smtp-mail.outlook.com`
- **Yahoo**: `smtp.mail.yahoo.com`
- **Custom domain**: Use your SMTP server details

## Features Implemented

### Backend Features
- ✅ User registration with email verification
- ✅ JWT-based authentication
- ✅ Email verification token generation
- ✅ SMTP email sending
- ✅ Email verification endpoint
- ✅ Resend verification email functionality
- ✅ Login requires email verification
- ✅ Token expiration handling

### Frontend Features
- ✅ Updated authentication system
- ✅ Email verification page
- ✅ Signup with additional fields (name, mobile)
- ✅ Improved error handling
- ✅ Resend verification functionality
- ✅ Token-based authentication
- ✅ Local storage for token persistence

## API Endpoints

### Authentication Endpoints
- `POST /api/auth/signup` - Register new user
- `POST /api/auth/login` - Login user
- `POST /api/auth/verify-email` - Verify email with token
- `POST /api/auth/resend-verification` - Resend verification email
- `GET /api/auth/me` - Get current user
- `POST /api/auth/logout` - Logout user
- `POST /api/auth/refresh` - Refresh access token

## User Flow

1. **Signup**: User creates account → Verification email sent
2. **Email Verification**: User clicks link → Email verified → Can login
3. **Login**: User logs in with verified email → Access granted
4. **Resend**: If email not received → User can request new verification email

## Testing

1. Start the backend server
2. Start the frontend application
3. Create a new account
4. Check your email for verification link
5. Click the verification link
6. Login with your verified account

## Security Features

- Secure token generation using `secrets.token_urlsafe(32)`
- Token expiration (24 hours by default)
- Password hashing with bcrypt
- JWT token authentication
- Email verification required for login
- Rate limiting on verification endpoints (can be added)

## Troubleshooting

### Email Not Sending
- Check SMTP credentials
- Verify 2FA is enabled for Gmail
- Check firewall/network settings
- Verify SMTP port (587 for TLS)

### Verification Link Not Working
- Check token expiration
- Verify frontend URL configuration
- Check database connection
- Verify token format

### Login Issues
- Ensure email is verified
- Check JWT secret key
- Verify token expiration settings
- Check database user status 