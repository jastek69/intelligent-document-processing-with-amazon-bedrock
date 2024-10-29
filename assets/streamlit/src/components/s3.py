from pathlib import Path

import boto3
import botocore

S3_CLIENT = boto3.client("s3")


def create_presigned_url(s3_path, expiration=3600):
    """
    Generate a presigned URL to share an S3 object.

    Parameters
    ----------
    s3_path : string
        Full path to the file in S3 (including bucket and key).
    expiration: int
        Time in seconds for the URL to remain valid. By default, 3600.

    Returns
    -------
    str
        Presigned URL as string. If error, returns None.
    """

    # Return the URL if it is not an S3 path
    if not s3_path.startswith("s3://"):
        return s3_path

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

    # Generate a presigned URL for the S3 object
    s3_bucket, s3_name = split_s3_path(s3_path)
    file_params = {"Bucket": s3_bucket, "Key": s3_name}

    file_format = Path(s3_name).suffix[1:]
    if file_format in CONTENT_TYPES:
        file_params["ResponseContentType"] = CONTENT_TYPES[file_format]

    try:
        response = S3_CLIENT.generate_presigned_url(
            "get_object",
            Params=file_params,
            ExpiresIn=expiration,
        )
    except botocore.exceptions.ClientError as error:
        print(error)
        return None

    # The response contains the presigned URL
    return response


def split_s3_path(s3_path: str):
    """
    Splits an S3 path into bucket and key.

    Parameters
    ----------
    s3_path : str
        S3 path (including bucket and key)

    Returns
    -------
    bucket : str
        S3 bucket
    key : str
        S3 key
    """

    # split into parts
    path_parts = s3_path.replace("s3://", "").split("/")

    # extract bucket and key
    bucket = path_parts.pop(0)
    key = "/".join(path_parts)

    return bucket, key
