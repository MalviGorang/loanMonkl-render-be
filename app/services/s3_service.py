# backend/app/services/s3_service.py
# AWS S3 integration for document uploads

import boto3
from botocore.exceptions import ClientError
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")


def generate_presigned_url(
    student_id: str, document_type: str, file_name: str, expiration: int = 900
) -> Optional[str]:
    """Generate a pre-signed URL for uploading a document to S3."""
    try:
        url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": f"student-{student_id}/{document_type}/{file_name}",
            },
            ExpiresIn=expiration,
        )
        return url
    except ClientError as e:
        logger.error(f"Error generating pre-signed URL: {e}")
        return None
