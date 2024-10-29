"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Docker Lambda
"""

#########################
#        IMPORTS
#########################

import json
import logging
import os
import pathlib
import sys

import boto3
import nltk
from langchain_community.document_loaders import (
    TextLoader,
    UnstructuredExcelLoader,
    UnstructuredHTMLLoader,
    UnstructuredPowerPointLoader,
    UnstructuredWordDocumentLoader,
)
from utils import get_document_text

#########################
#       CONSTANTS
#########################

LOGGER = logging.Logger("READ_OFFICE", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


S3_BUCKET = os.environ["BUCKET_NAME"]

NLTK_DATA = "/tmp/nltk_data"
TMP_DIR = "/tmp"

PREFIX_ORIGINALS = "originals"
PREFIX_PROCESSED = "processed"

POWERPOINT_EXTENSIONS = json.loads(os.environ["POWERPOINT_EXTENSIONS"])
WORD_EXTENSIONS = json.loads(os.environ["WORD_EXTENSIONS"])
EXCEL_EXTENSIONS = json.loads(os.environ["EXCEL_EXTENSIONS"])
HTML_EXTENSIONS = json.loads(os.environ["HTML_EXTENSIONS"])
MARKDOWN_EXTENSIONS = json.loads(os.environ["MARKDOWN_EXTENSIONS"])

S3_CLIENT = boto3.client("s3")
nltk.download("punkt", download_dir=NLTK_DATA)
nltk.download("averaged_perceptron_tagger", download_dir=NLTK_DATA)


#########################
#     LAMBDA HANDLER
#########################


def lambda_handler(event, context):  # noqa: C901
    # parse event
    if "requestContext" in event:
        LOGGER.info("Received HTTP request.")
        body = json.loads(event["body"])
    else:  # step functions invocation
        body = event["body"]
    LOGGER.info(f"Received input: {body}")

    file_name = body["file_name"]
    file_key = f"{PREFIX_PROCESSED}/{file_name.split('/', 1)[-1].rsplit('.')[0]}.txt"
    LOGGER.info(f"file_name: {file_name}")

    doc_text = get_document_text(
        bucket_name=S3_BUCKET,
        prefix=PREFIX_PROCESSED,
        file_name=f"{file_name.split('/', 1)[-1].rsplit('.')[0]}.txt",
        max_length=None,
    )

    if doc_text is None:
        object_path = pathlib.Path(file_name)
        local_file_path = f"/tmp/{file_name.split('/', 1)[-1]}"

        # load document
        LOGGER.info(f"Loading doc {file_name}")
        LOGGER.info(f"Local file_path {local_file_path}")
        S3_CLIENT.download_file(S3_BUCKET, file_name, local_file_path)

        extension = object_path.suffix

        if extension in POWERPOINT_EXTENSIONS:
            loader = UnstructuredPowerPointLoader(local_file_path, mode="elements")
        elif extension in WORD_EXTENSIONS:
            loader = UnstructuredWordDocumentLoader(local_file_path, mode="elements")
        elif extension in EXCEL_EXTENSIONS:
            loader = UnstructuredExcelLoader(local_file_path, mode="elements")
        elif extension in HTML_EXTENSIONS:
            loader = UnstructuredHTMLLoader(local_file_path, mode="elements")
        elif extension in MARKDOWN_EXTENSIONS:
            loader = TextLoader(local_file_path)

        data = loader.load()

        LOGGER.info(f"data: {data}")

        pagne_nb = 1
        raw_text = f"[page {pagne_nb}]\n"

        for element in data:
            if "page_number" in element.metadata and element.metadata["page_number"] > pagne_nb:
                pagne_nb = element.metadata["page_number"]
                raw_text += f"[page {pagne_nb}]\n"

            if element.page_content and element.page_content.strip() != "":
                raw_text += element.page_content + "\n"

        S3_CLIENT.put_object(Body=raw_text.encode(), Bucket=S3_BUCKET, Key=file_key)

        LOGGER.info(f"Finished processing doc {file_name}")

    else:
        LOGGER.info(f"Skipping doc {file_key}, file already processed")

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "file_key": file_key,
                "original_file_name": file_name,
            }
        ),
    }
