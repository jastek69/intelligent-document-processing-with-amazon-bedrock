"""
Copyright © Amazon.com and Affiliates
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys
import time

import aiohttp
import boto3
import streamlit as st

LOGGER = logging.Logger("ECS", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)

API_URI = os.environ.get("API_URI")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN")

REQUEST_TIMEOUT = 900


def invoke_step_function(
    file_keys: list[str],
    attributes: list[dict],
    instructions: str = "",
    few_shots: list[dict] = [],  # noqa: B006
    model_id: str = "anthropic.claude-v2:1",
    parsing_mode: str = "Amazon Textract",
    temperature: float = 0.0,
) -> str:
    """
    Invoke a step function boto3 call

    Parameters
    ----------
    file_keys : list[str]
        S3 keys for input documents
    attributes : list[dict]
        List of attribute dictionaries to be extracted
    instructions : str
        Optional high-level instructions, by default ""
    few_shots: list[dict]
        Optional list of few shot examples (input and output pairs)
    model_id : str, optional
        ID of the language model, by default "anthropic.claude-v2.1"
    parsing_mode : str, optional
        Parsing algorithm to use, by default "Amazon Textract"
    temperature : float, optional
        Model inference temperature, by default 0.0
    """

    client = boto3.client("stepfunctions")

    data = json.dumps(
        {
            "documents": file_keys,
            "attributes": attributes,
            "instructions": instructions,
            "few_shots": few_shots,
            "parsing_mode": parsing_mode,
            "model_params": {
                "model_id": model_id,
                "temperature": temperature,
            },
        }
    )

    try:
        response = client.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            input=data,
        )
        execution_arn = response["executionArn"]

        while True:
            time.sleep(int(1))

            response = client.describe_execution(executionArn=execution_arn)
            status = response["status"]
            print(f"Status: {status}")

            if status == "FAILED":
                error_info = json.loads(response.get("cause", "{}"))
                raise Exception(f"Step function execution failed: {error_info.get('errorMessage', 'Unknown error')}")

            if status == "SUCCEEDED":
                outputs = json.loads(response["output"])
                for output in outputs:
                    if "error" in output:
                        error_cause = json.loads(output["error"].get("Cause", "{}"))
                        error_message = error_cause.get("errorMessage", "Unknown error")
                        raise Exception(f"Error in processing: {error_message}")

                    if "llm_answer" not in output:
                        raise Exception("No LLM answer found in the output")

                    parsed_response = output["llm_answer"]["answer"]
                    parsed_response["_file_name"] = output["llm_answer"]["original_file_name"].split("/", 1)[-1]
                    st.session_state["parsed_response"].append(parsed_response)
                    st.session_state["raw_response"].append(output["llm_answer"]["raw_answer"])
                break

    except Exception as e:
        raise Exception(f"Error in step function execution: {str(e)}")  # noqa: B904


async def get_file_name(file, prefix: str = "") -> str:
    """
    Generate or extract file name with optional prefix

    Parameters
    ----------
    file : file-like object or str
        File to upload
    prefix : str, optional
        Prefix for the file name, by default ""
    """
    if isinstance(file, str):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_name = f"document_{timestamp}.txt"
        LOGGER.debug(f"Created timestamp-based filename for text input: {file_name}")
    else:
        file_name = file.name
        LOGGER.debug(f"Using original filename: {file_name}")

    return f"{prefix}/{file_name}" if prefix else file_name


async def get_presigned_url(session: aiohttp.ClientSession, file_name: str, access_token: str) -> dict:
    """
    Get presigned URL from API Gateway

    Parameters
    ----------
    session : aiohttp.ClientSession
        Client session for making HTTP requests
    file_name : str
        Name of the file to upload
    access_token : str
        Access token for API Gateway
    """
    LOGGER.info("Requesting presigned URL from API Gateway")
    async with session.post(
        url=API_URI + "/url",
        json={"file_name": file_name},
        headers={"Authorization": access_token},
        timeout=REQUEST_TIMEOUT,
    ) as response:
        LOGGER.debug(f"Presigned URL response status: {response.status}")
        response.raise_for_status()
        response_data = await response.json()
        LOGGER.debug(f"Presigned URL response data: {response_data}")
        return response_data


async def prepare_upload_form(file, file_name: str, presigned_fields: dict) -> aiohttp.FormData:
    """
    Prepare form data for S3 upload

    Parameters
    ----------
    file : file-like object or str
        File to upload
    file_name : str
        Name of the file to upload
    presigned_fields : dict
        Fields from the presigned URL
    """
    LOGGER.info("Preparing file content and form data")
    # Prepare file content
    file_content = file.encode() if isinstance(file, str) else file.getvalue()

    # Create form with S3 fields
    form = aiohttp.FormData()
    for field_name, field_value in presigned_fields.items():
        form.add_field(field_name, field_value)

    # Add file content
    form.add_field("file", file_content, filename=file_name, content_type="application/octet-stream")
    return form


async def upload_to_s3(session: aiohttp.ClientSession, url: str, form: aiohttp.FormData) -> None:
    """
    Upload form data to S3

    Parameters
    ----------
    session : aiohttp.ClientSession
        Client session for making HTTP requests
    url : str
        URL to upload the file to
    form : aiohttp.FormData
        Form data to upload
    """
    LOGGER.info("Uploading to S3")
    async with session.post(
        url=url,
        data=form,
        timeout=REQUEST_TIMEOUT,
    ) as response:
        LOGGER.debug(f"S3 upload response status: {response.status}")
        LOGGER.debug(f"S3 upload response headers: {response.headers}")
        response.raise_for_status()
        LOGGER.info("Upload successful")


async def invoke_file_upload_async(
    file,
    access_token: str,
    prefix="",
) -> str:
    """
    Async version of get presigned URL via API Gateway and upload the file to S3

    Parameters
    ----------
    file : file-like object or str
        File to upload
    access_token : str
        Access token for API Gateway
    prefix : str, optional
        Prefix for the file name, by default ""
    """
    LOGGER.info(f"Starting file upload process for file: {getattr(file, 'name', 'text input')}")

    try:
        file_name = await get_file_name(file, prefix)
        file_content = file.encode() if isinstance(file, str) else file.getvalue()

        async with aiohttp.ClientSession() as session:
            response_data = await get_presigned_url(session, file_name, access_token)

            if "post" in response_data:
                # Create multipart form data
                data = aiohttp.MultipartWriter("form-data")

                # Add all fields from presigned URL first
                fields = response_data["post"]["fields"]
                for field_name, field_value in fields.items():
                    part = data.append(field_value)
                    part.set_content_disposition("form-data", name=field_name)

                # Add file content last
                part = data.append(file_content)
                part.set_content_disposition("form-data", name="file", filename=file_name)
                part.headers["Content-Type"] = "application/octet-stream"

                async with session.post(
                    url=response_data["post"]["url"],
                    data=data,
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    LOGGER.debug(f"S3 upload response status: {response.status}")
                    response.raise_for_status()
                    return fields["key"]
            else:
                raise ValueError("Invalid presigned URL response format")
    except Exception as e:
        LOGGER.error(f"Error during upload: {str(e)}")
        raise
