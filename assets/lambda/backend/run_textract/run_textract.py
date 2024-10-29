"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Lambda that runs Textract and saves text to S3
"""

#########################
#   LIBRARIES & LOGGER
#########################

import io
import json
import logging
import os
import sys

import boto3
from textractor import Textractor
from textractor.data.constants import TextractFeatures
from utils import extract_content_by_pages, get_document_text

LOGGER = logging.Logger("TEXTRACT", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


#########################
#       CONSTANTS
#########################

S3_BUCKET = os.environ["BUCKET_NAME"]
PREFIX_PROCESSED = "processed"

S3_CLIENT = boto3.client("s3")
TEXTRACT_CLIENT = boto3.client("textract")
TEXTRACT_REGION = os.environ["TEXTRACT_REGION"]
USE_TABLE = os.environ["USE_TABLE"]


#########################
#        HANDLER
#########################


def lambda_handler(event, context):  # noqa: C901
    """
    Lambda handler
    """

    # parse event
    if "requestContext" in event:
        LOGGER.info("Received HTTP request.")
        body = json.loads(event["body"])
    else:  # step functions invocation
        body = event["body"]
    LOGGER.info(f"Received input: {body}")

    ### EXTRACT TEXT

    file_name = body["file_name"]
    file_key = f"{PREFIX_PROCESSED}/{file_name.split('/', 1)[-1].rsplit('.')[0]}.txt"
    csv_tables = []

    # check if processed file exists
    doc_text = get_document_text(
        bucket_name=S3_BUCKET,
        prefix=PREFIX_PROCESSED,
        file_name=f"{file_name.split('/', 1)[-1].rsplit('.')[0]}.txt",
        max_length=None,
    )

    # check if file is a TXT
    if doc_text is None and file_name.endswith(".txt"):
        s3_resource = boto3.resource("s3")
        content_object = s3_resource.Object(S3_BUCKET, file_name)
        doc_text = content_object.get()["Body"].read().decode("utf-8")
        S3_CLIENT.put_object(Body=doc_text.encode(), Bucket=S3_BUCKET, Key=file_key)
        LOGGER.info(f"Uploaded text to: {file_key}")

    # run Textract
    if doc_text is None:
        extractor = Textractor(region_name=TEXTRACT_REGION)
        extractor_kwargs = {"features": [TextractFeatures.TABLES, TextractFeatures.LAYOUT], "save_image": False}
        if not USE_TABLE:
            extractor_kwargs = {"features": [TextractFeatures.LAYOUT], "save_image": False}
        file_source = f"s3://{S3_BUCKET}/{file_name}"
        parsed_document = extractor.start_document_analysis(file_source, **extractor_kwargs)

        # extract text content
        doc_text, tables = extract_content_by_pages(parsed_document, LOGGER)

        # save processed text to S3
        S3_CLIENT.put_object(Body=doc_text.encode(), Bucket=S3_BUCKET, Key=file_key)
        LOGGER.info(f"Uploaded text to: {file_key}")
        for title, table in tables.items():
            csv_title = title.replace("Title:", "").strip() + ".csv"
            table_key = file_key.split(".txt")[0] + "/" + csv_title
            csv_buffer = io.StringIO()
            table.to_csv(csv_buffer)
            S3_CLIENT.put_object(Body=csv_buffer.getvalue(), Bucket=S3_BUCKET, Key=table_key)
            LOGGER.info(f"Uploaded {title} table to: {table_key}")
            csv_tables.append(table_key)

    # load cached file
    else:
        LOGGER.info("Found processed file. Skipping Textract...")
        if USE_TABLE:
            table_prefix = file_key.split(".txt")[0]
            LOGGER.info(f"Found processed file. Skipping Textract. Retrieve csv tables with prefix {table_prefix}...")
            s3_response = S3_CLIENT.list_objects_v2(Bucket=S3_BUCKET, Prefix=f"{table_prefix}/")
            try:
                related_files = [obj["Key"] for obj in s3_response["Contents"]]
                csv_tables = [f for f in related_files if f.split(".")[-1] == "csv"]
            except KeyError:
                LOGGER.debug("No related table found")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "file_key": file_key,
                "csv_tables": csv_tables,
                "original_file_name": file_name,
            }
        ),
    }
