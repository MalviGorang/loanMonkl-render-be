# backend/app/services/s3_service.py
# AWS S3 integration for document uploads

import boto3
from botocore.exceptions import ClientError
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize S3 client
try:
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not aws_access_key or not aws_secret_key:
        logger.warning(
            "AWS credentials not provided. S3 functionality will be disabled."
        )
        s3_client = None
    else:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
        )
        logger.info("S3 client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize S3 client: {e}")
    s3_client = None

BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
if not BUCKET_NAME:
    logger.warning("S3_BUCKET_NAME not configured. Document upload will not work.")


def generate_presigned_url(
    student_id: str, document_type: str, file_name: str, expiration: int = 900
) -> Optional[str]:
    """Generate a pre-signed URL for uploading a document to S3."""
    if not s3_client:
        logger.error("S3 client not initialized - missing AWS credentials")
        return None

    if not BUCKET_NAME:
        logger.error("S3 bucket name not configured")
        return None

    try:
        # Sanitize the S3 key path
        safe_key = f"student-{student_id}/{document_type}/{file_name}"

        url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": safe_key,
                "ContentType": "application/octet-stream",  # Add content type restriction
            },
            ExpiresIn=expiration,
        )
        logger.info(f"Generated pre-signed URL for key: {safe_key}")
        return url
    except ClientError as e:
        logger.error(f"Error generating pre-signed URL: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error generating pre-signed URL: {e}")
        return None
