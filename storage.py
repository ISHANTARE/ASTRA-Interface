"""
ASTRA-Interface Platform — storage.py
AWS S3 & Local Storage Abstraction
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Boto3 is imported optionally or conditionally
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None

AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET")
AWS_REGION    = os.environ.get("AWS_REGION", "us-east-1")
S3_CUSTOM_URL = os.environ.get("S3_CUSTOM_URL") # e.g. CloudFront distribution URL

_s3_client = None

def get_s3_client():
    global _s3_client
    if not AWS_S3_BUCKET or not boto3:
        return None
        
    if _s3_client is None:
        try:
            _s3_client = boto3.client("s3", region_name=AWS_REGION)
            logger.info(f"Initialized AWS S3 Client for bucket: {AWS_S3_BUCKET}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            _s3_client = None
    return _s3_client

def get_static_prefix() -> str:
    """
    Returns the URL prefix for static assets.
    If S3 is configured, this can return the CloudFront or S3 bucket URL.
    Otherwise, returns '/static' for WhiteNoise.
    """
    if AWS_S3_BUCKET:
        if S3_CUSTOM_URL:
            return S3_CUSTOM_URL.rstrip('/')
        return f"https://{AWS_S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/static"
    return "/static"

def upload_file_object(file_obj, object_name: str) -> bool:
    """Uploads a file-like object to S3 or a local dummy cache if not configured."""
    client = get_s3_client()
    if client:
        try:
            client.upload_fileobj(file_obj, AWS_S3_BUCKET, object_name)
            return True
        except (BotoCoreError, ClientError) as e:
            logger.error(f"Failed uploading {object_name} to S3: {e}")
            return False
    else:
        # Local fallback simulation
        logger.info(f"Local Storage Fallback: Skipping file upload for {object_name}")
        return True

def get_file_content(object_name: str) -> bytes | None:
    """Fetch an object from S3, else from local simulation (not fully implemented for local yet)."""
    client = get_s3_client()
    if client:
        try:
            response = client.get_object(Bucket=AWS_S3_BUCKET, Key=object_name)
            return response['Body'].read()
        except (BotoCoreError, ClientError) as e:
            logger.error(f"Failed downloading {object_name} from S3: {e}")
            return None
    else:
         # Local fallback simulation
         logger.info(f"Local Storage Fallback: cannot retrieve true {object_name}")
         return None
