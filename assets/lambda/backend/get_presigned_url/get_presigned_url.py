"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Lambda that generates a presigned URL for file(s) to be uploaded to S3
"""

import json
import logging
import os
import sys

import boto3
from botocore.client import Config

LOGGER = logging.Logger("PRESIGNED-URL", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)

EXPIRATION_IN_SECONDS = 3600
S3_BUCKET = os.environ["BUCKET_NAME"]
PREFIX = "originals"


def lambda_handler(event, context):
    """
    Lambda handler
    """

    # parse event
    LOGGER.info("Starting execution of lambda_handler()")
    event = json.loads(event["body"])
    file_name = event["file_name"]

    # get S3 key
    s3_key = f"{PREFIX}/{file_name}"
    LOGGER.info(f"S3 path: {S3_BUCKET}/{s3_key}")

    # generate presigned URL
    s3 = boto3.client("s3", config=Config(signature_version="s3v4"))
    presigned_post = s3.generate_presigned_post(
        Bucket=S3_BUCKET,
        Key=s3_key,
        ExpiresIn=EXPIRATION_IN_SECONDS,
    )
    LOGGER.info(f"Presigned URL: {presigned_post}")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"post": presigned_post}),
    }
