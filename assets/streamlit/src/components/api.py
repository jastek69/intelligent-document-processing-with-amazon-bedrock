"""
Helper classes for LLM inference
"""

from __future__ import annotations

import datetime
import json
import os
import time

import aiohttp
import boto3
import streamlit as st

API_URI = os.environ.get("API_URI")
STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN")

REQUEST_TIMEOUT = 900


def invoke_step_function(
    file_keys: list[str],
    attributes: list[dict],
    instructions: str = "",
    few_shots: list[dict] = [],
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
        raise Exception(f"Error in step function execution: {str(e)}")


async def invoke_file_upload_async(
    file,
    access_token: str,
    prefix="",
) -> str:
    """
    Async version of get presigned URL via API Gateway and upload the file to S3
    """
    if isinstance(file, str):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_name = f"document_{timestamp}.txt"
    else:
        file_name = file.name

    params = {"file_name": f"{prefix}/{file_name}" if prefix else file_name}

    async with aiohttp.ClientSession() as session:
        # Get presigned URL
        async with session.post(
            url=API_URI + "/url",
            json=params,
            headers={"Authorization": access_token},
            timeout=REQUEST_TIMEOUT,
        ) as response:
            response.raise_for_status()
            response_data = await response.json()

        # Upload file to S3
        if "post" in response_data:
            form = aiohttp.FormData()
            # Add all fields from presigned URL - fields must be added before file
            for field_name, field_value in response_data["post"]["fields"].items():
                form.add_field(field_name, field_value)
            # Add the file as the last field
            if isinstance(file, str):
                form.add_field("file", file.encode(), filename=file_name)
            else:
                form.add_field("file", file.getvalue(), filename=file_name)

            async with session.post(
                url=response_data["post"]["url"],
                data=form,
                timeout=REQUEST_TIMEOUT,
            ) as post_response:
                post_response.raise_for_status()

        return response_data["post"]["fields"]["key"]
