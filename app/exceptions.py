from fastapi import HTTPException, status

class DuplicateEmailError(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists. Please use a different email or try logging in."
        )

class MongoDBDuplicateKeyError(HTTPException):
    def __init__(self, key_value=None, code=None):
        # Store the error code and key_value for potential use in error handling
        self.mongo_code = code
        self.key_value = key_value
        
        detail = "Duplicate key error encountered."
        if key_value and 'email' in key_value:
            detail = f"Student with email '{key_value['email']}' already exists. If this is a new student with the same email, ensure the mobile number is different. If updating an existing student, both email and mobile number must match."
        
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )

class StudentExistsError(HTTPException):
    def __init__(self, email, action="create"):
        self.email = email
        if action == "create":
            detail = f"Student with email '{email}' already exists. To update, both email and mobile number must match."
        else:
            detail = f"Cannot update student with email '{email}'. Email exists but mobile number doesn't match."
        
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
