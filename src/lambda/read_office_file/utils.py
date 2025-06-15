"""
Copyright © Amazon.com and Affiliates
"""

import re
from pathlib import Path

import boto3
import s3fs
from botocore.config import Config

config = Config(signature_version="s3v4")

# content type [enables opening file in browser]
CONTENT_TYPES = {
    "bmp": "image/bmp",
    "csv": "text/csv",
    "gif": "image/gif",
    "htm": "text/html",
    "html": "text/html",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "json": "application/json",
    "png": "image/png",
    "pdf": "application/pdf",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "txt": "text/plain",
}

#########################
#   S3
#########################

S3_CLIENT = boto3.client("s3", config=config)


def clean_text_snippet(text: str, max_length: int = None) -> str:
    """
    Clean a text snippet

    Parameters
    ----------
    text : str
        Text snippet to be cleaned
    max_length : None
        Maximum no. characters in the text snippet, by default None
    Returns
    -------
    str
        Cleaned text snippet
    """

    special_symbols = ["™", "®", "©"]
    for sym in special_symbols:
        text = re.sub(sym, "", text)

    text = text.strip()

    if max_length is not None:
        if max_length > len(text):
            text = f"{text[:max_length]}..."

    return text


def get_document_text(
    bucket_name: str,
    prefix: str,
    file_name: str,
    max_length: int = None,
) -> str:
    """
    Return document text

    Parameters
    ----------
    bucket_name : str
        S3 bucket name
    prefix : str
        S3 prefix
    file_name : str
        File name
    max_length : None
        Maximum no. characters in the text snippet, by default None
    Returns
    -------
    str
        Cleaned text snippet
    """

    doc_uri = f"{prefix}/{file_name}"

    # read document from S3
    fs = s3fs.S3FileSystem(anon=False)
    try:
        with fs.open(f"{bucket_name}/{doc_uri}", "rb", encoding="utf-8") as f:
            s3_object = f.read()
    except:  # noqa: E722
        print(f"Could not find {doc_uri} in {bucket_name}")
        return None
    doc_text = s3_object.decode("utf-8")

    return clean_text_snippet(
        text=doc_text,
        max_length=max_length,
    )


def upload_to_s3(s3_bucket, s3_key, local_path: str):
    """
    Uploads a file from S3.

    Parameters
    ----------
    s3_bucket : str
        S3 destination bucket
    s3_key : str
        S3 destination key
    local_path : str
        Local path to the file
    """
    file_format = Path(s3_key).suffix[1:]
    if file_format in CONTENT_TYPES:
        ExtraArgs = {
            "ContentType": CONTENT_TYPES[file_format],
        }
    else:
        ExtraArgs = None

    # upload the file
    S3_CLIENT.upload_file(
        local_path,
        s3_bucket,
        s3_key,
        ExtraArgs=ExtraArgs,
    )
