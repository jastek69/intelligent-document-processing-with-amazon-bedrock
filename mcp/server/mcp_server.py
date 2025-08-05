"""
Tabulate MCP Server - Exposes document attribute extraction via MCP protocol
"""

import json
import time
import boto3
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
from mcp.server.fastmcp import FastMCP

# Initialize MCP server with stateless HTTP for AgentCore Runtime compatibility
mcp = FastMCP(host="0.0.0.0", stateless_http=True)

# Initialize AWS clients
stepfunctions_client = boto3.client("stepfunctions")
s3_client = boto3.client("s3")


def discover_step_functions(region, account_id):
    """Discover Step Functions state machine"""
    try:
        sf_client = boto3.client("stepfunctions", region_name=region)
        paginator = sf_client.get_paginator("list_state_machines")
        for page in paginator.paginate():
            for sm in page["stateMachines"]:
                if "idp-bedrock" in sm["name"].lower():
                    print(f"✅ Discovered Step Functions: {sm['stateMachineArn']}")
                    return sm["stateMachineArn"]
    except Exception as e:
        print(f"⚠️  Could not discover Step Functions: {e}")
    return None


def discover_s3_bucket(region):
    """Discover S3 bucket"""
    try:
        s3_client = boto3.client("s3", region_name=region)
        response = s3_client.list_buckets()
        for bucket in response["Buckets"]:
            if "idp-bedrock" in bucket["Name"].lower() and "data" in bucket["Name"].lower():
                print(f"✅ Discovered S3 bucket: {bucket['Name']}")
                return bucket["Name"]
    except Exception as e:
        print(f"⚠️  Could not discover S3 bucket: {e}")
    return None


def get_fallback_values(region, account_id):
    """Get fallback configuration values"""
    state_machine_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:idp-bedrock-StepFunctions"
    bucket_name = f"idp-bedrock-data-{account_id}"
    print(f"⚠️  Using fallback Step Functions ARN: {state_machine_arn}")
    print(f"⚠️  Using fallback bucket name: {bucket_name}")
    return state_machine_arn, bucket_name


def get_hardcoded_fallbacks():
    """Get hardcoded fallback values as last resort"""
    state_machine_arn = "arn:aws:states:us-east-1:471112811980:stateMachine:idp-bedrock-StepFunctions"
    bucket_name = "idp-bedrock-data-471112811980"
    print("⚠️  Using hardcoded fallbacks")
    return state_machine_arn, bucket_name


def get_configuration():
    """Get configuration from environment variables or AWS discovery"""
    state_machine_arn = os.getenv("STATE_MACHINE_ARN")
    bucket_name = os.getenv("BUCKET_NAME")

    # If environment variables are not set, try to discover from AWS
    if not state_machine_arn or not bucket_name:
        print("⚠️  Environment variables not set, attempting AWS discovery...")
        try:
            boto_session = boto3.Session()
            region = boto_session.region_name
            account_id = boto3.client("sts").get_caller_identity()["Account"]

            if not state_machine_arn:
                state_machine_arn = discover_step_functions(region, account_id)

            if not bucket_name:
                bucket_name = discover_s3_bucket(region)

            # Use fallback naming patterns if discovery failed
            if not state_machine_arn or not bucket_name:
                fallback_sm, fallback_bucket = get_fallback_values(region, account_id)
                if not state_machine_arn:
                    state_machine_arn = fallback_sm
                if not bucket_name:
                    bucket_name = fallback_bucket

        except Exception as e:
            print(f"❌ Error during AWS discovery: {e}")
            state_machine_arn, bucket_name = get_hardcoded_fallbacks()

    return state_machine_arn, bucket_name


# Get configuration
STATE_MACHINE_ARN, BUCKET_NAME = get_configuration()

SUPPORTED_MODELS = [
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "us.anthropic.claude-3-haiku-20240307-v1:0",
    "us.amazon.nova-premier-v1:0",
    "us.amazon.nova-pro-v1:0",
    "us.amazon.nova-lite-v1:0",
]


def is_local_file_path(path: str) -> bool:
    """Check if a path is a local file path (not an S3 key)"""
    # Check if it's an absolute path or relative path that exists locally
    path_obj = Path(path)
    return (
        path_obj.is_absolute()  # Absolute paths like /home/user/doc.pdf
        or path.startswith("./")  # Relative paths like ./doc.pdf
        or path.startswith("../")  # Parent directory paths like ../doc.pdf
        or ("/" not in path and path_obj.exists())  # Simple filenames that exist locally
    )


def upload_local_file_to_s3(local_path: str, bucket_name: str) -> str:
    """
    Upload a local file to S3 and return the S3 key

    Args:
        local_path: Local file path
        bucket_name: S3 bucket name

    Returns:
        S3 key for the uploaded file

    Raises:
        Exception: If upload fails
    """
    if not bucket_name:
        raise Exception("S3 bucket not configured. Cannot upload local files.")

    path_obj = Path(local_path)

    if not path_obj.exists():
        raise Exception(f"Local file does not exist: {local_path}")

    if not path_obj.is_file():
        raise Exception(f"Path is not a file: {local_path}")

    # Generate a unique S3 key to avoid conflicts
    file_extension = path_obj.suffix
    unique_id = str(uuid.uuid4())[:8]
    s3_key = f"uploaded/{path_obj.stem}_{unique_id}{file_extension}"

    try:
        # Upload the file to S3
        s3_client.upload_file(str(path_obj), bucket_name, s3_key)
        print(f"📤 Uploaded {local_path} to s3://{bucket_name}/{s3_key}")
        return s3_key

    except Exception as e:
        raise Exception(f"Failed to upload {local_path} to S3: {str(e)}") from e


def process_document_paths(documents: List[str]) -> tuple[List[str], List[str]]:
    """
    Process document paths, uploading local files to S3 if needed

    Args:
        documents: List of document paths (mix of local paths and S3 keys)

    Returns:
        Tuple of (processed_s3_keys, upload_info)
    """
    processed_documents = []
    upload_info = []

    for doc_path in documents:
        if is_local_file_path(doc_path):
            try:
                s3_key = upload_local_file_to_s3(doc_path, BUCKET_NAME)
                processed_documents.append(s3_key)
                upload_info.append(f"Uploaded {doc_path} → s3://{BUCKET_NAME}/{s3_key}")
            except Exception as e:
                raise Exception(f"Failed to process local file {doc_path}: {str(e)}") from e
        else:
            # Assume it's already an S3 key
            processed_documents.append(doc_path)
            upload_info.append(f"Using existing S3 key: {doc_path}")

    return processed_documents, upload_info


def run_idp_bedrock_api(
    state_machine_arn: str,
    documents: Union[str, Sequence[str]],
    attributes: Sequence[Dict[str, Any]],
    parsing_mode: Optional[str] = "Amazon Textract",
    instructions: Optional[str] = "",
    few_shots: Optional[Sequence[Dict[str, Any]]] = None,
    model_params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Run IDP Bedrock to extract custom attributes and scores from the text(s)
    This mirrors the functionality from demo/utils.py
    """
    if few_shots is None:
        few_shots = []

    if model_params is None:
        model_params = {
            "model_id": "us.anthropic.claude-3-haiku-20240307-v1:0",
            "output_length": 2000,
            "temperature": 0.0,
        }

    if isinstance(documents, str):
        documents = [documents]

    event = json.dumps(
        {
            "attributes": attributes,
            "documents": documents,
            "instructions": instructions,
            "few_shots": few_shots,
            "model_params": model_params,
            "parsing_mode": parsing_mode,
        }
    )

    response = stepfunctions_client.start_execution(
        stateMachineArn=state_machine_arn,
        input=event,
    )

    execution_arn = response["executionArn"]

    while True:
        time.sleep(1)

        response = stepfunctions_client.describe_execution(executionArn=execution_arn)
        status = response["status"]

        if status == "FAILED":
            error_details = response.get("error", "Unknown error")
            raise Exception(f"Step Function execution failed: {error_details}")

        if status == "SUCCEEDED":
            outputs = json.loads(response["output"])
            results = []
            for output in outputs:
                results.append(
                    {"file_key": output["llm_answer"]["file_key"], "attributes": output["llm_answer"]["answer"]}
                )
            return results


@mcp.tool()
def extract_document_attributes(
    documents: List[str],
    attributes: List[Dict[str, Any]],
    parsing_mode: str = "Amazon Textract",
    instructions: str = "",
    few_shots: List[Dict[str, Any]] = None,
    model_params: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Extract custom attributes from documents using Amazon Bedrock and AWS document processing services.

    This tool processes documents (text, PDF, images, Office files) and extracts specified attributes
    using large language models. It supports various parsing modes and can handle batch processing.

    Args:
        documents: List of document paths - S3 keys
            (e.g., ["originals/email_1.txt"])
        attributes: List of attribute definitions, each containing:
            - name: str - Name of the attribute (e.g., "customer_name")
            - description: str - Description of what to extract
            - type: str (optional) - "auto", "character", "number", or "true/false"
        parsing_mode: str - "Amazon Textract", "Amazon Bedrock LLM", or "Bedrock Data Automation"
        instructions: str - Optional high-level instructions for extraction
        few_shots: List of example input/output pairs for few-shot learning
        model_params: Dict with model configuration:
            - model_id: str - Bedrock model ID to use
            - output_length: int - Maximum output length
            - temperature: float - Model temperature (0.0-1.0)

    Returns:
        List of results, each containing:
            - file_key: str - The document that was processed
            - attributes: Dict - Extracted attributes as key-value pairs

    Example:
        extract_document_attributes(
            documents=["originals/email_1.txt"],
            attributes=[
                {"name": "customer_name", "description": "name of the customer who wrote the email"},
                {"name": "sentiment", "description": "sentiment score between 0 and 1"}
            ]
        )
    """
    if not STATE_MACHINE_ARN:
        raise Exception("STATE_MACHINE_ARN not configured. Please check deployment configuration.")

    if few_shots is None:
        few_shots = []

    if model_params is None:
        model_params = {
            "model_id": "us.anthropic.claude-3-haiku-20240307-v1:0",
            "output_length": 2000,
            "temperature": 0.0,
        }

    try:
        # Process document paths - upload local files to S3 if needed
        processed_documents, upload_info = process_document_paths(documents)

        results = run_idp_bedrock_api(
            state_machine_arn=STATE_MACHINE_ARN,
            documents=processed_documents,
            attributes=attributes,
            parsing_mode=parsing_mode,
            instructions=instructions,
            few_shots=few_shots,
            model_params=model_params,
        )

        return {
            "success": True,
            "results": results,
            "processed_documents": len(documents),
            "extracted_attributes": [attr["name"] for attr in attributes],
            "upload_info": upload_info,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "processed_documents": 0, "extracted_attributes": []}


@mcp.tool()
def get_extraction_status(execution_arn: str) -> Dict[str, Any]:
    """
    Check the status of a document attribute extraction operation.

    Args:
        execution_arn: The ARN of the Step Functions execution to check

    Returns:
        Dict containing:
            - status: str - "RUNNING", "SUCCEEDED", "FAILED", etc.
            - results: List - Results if completed successfully
            - error: str - Error message if failed
    """
    try:
        response = stepfunctions_client.describe_execution(executionArn=execution_arn)
        status = response["status"]

        result = {"status": status, "execution_arn": execution_arn}

        if status == "SUCCEEDED":
            outputs = json.loads(response["output"])
            results = []
            for output in outputs:
                results.append(
                    {"file_key": output["llm_answer"]["file_key"], "attributes": output["llm_answer"]["answer"]}
                )
            result["results"] = results

        elif status == "FAILED":
            result["error"] = response.get("error", "Unknown error")

        return result

    except Exception as e:
        return {"status": "ERROR", "error": str(e), "execution_arn": execution_arn}


@mcp.tool()
def list_supported_models() -> Dict[str, Any]:
    """
    Get the list of supported Amazon Bedrock models for document attribute extraction.

    Returns:
        Dict containing:
            - models: List of supported model IDs
            - default_model: The default model used if none specified
            - model_info: Additional information about model capabilities
    """
    return {
        "models": SUPPORTED_MODELS,
        "default_model": "us.anthropic.claude-3-haiku-20240307-v1:0",
        "model_info": {
            "claude_models": [m for m in SUPPORTED_MODELS if "claude" in m],
            "nova_models": [m for m in SUPPORTED_MODELS if "nova" in m],
            "recommended_for_speed": "us.anthropic.claude-3-haiku-20240307-v1:0",
            "recommended_for_quality": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
        },
    }


@mcp.tool()
def upload_and_extract_attributes(
    files: List[Dict[str, Any]],
    attributes: List[Dict[str, Any]],
    parsing_mode: str = "Amazon Bedrock LLM",
    instructions: str = "",
    few_shots: List[Dict[str, Any]] = None,
    model_params: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Upload files directly and extract attributes in one step.

    This tool accepts file content directly via HTTP and uploads to S3 automatically,
    then processes the files for attribute extraction.

    Args:
        files: List of file objects, each containing:
            - name: str - Original filename (e.g., "document.pdf")
            - content: str - Base64 encoded file content
            - mime_type: str (optional) - MIME type of the file
        attributes: List of attribute definitions to extract
        parsing_mode: Processing mode (default: "Amazon Bedrock LLM")
        instructions: Optional high-level instructions for extraction
        few_shots: List of example input/output pairs for few-shot learning
        model_params: Dict with model configuration

    Returns:
        Dict containing:
            - success: bool - Whether the operation succeeded
            - results: List - Extraction results for each file
            - upload_info: List - Information about uploaded files
            - processed_files: int - Number of files processed

    Example:
        upload_and_extract_attributes(
            files=[
                {
                    "name": "my_document.pdf",
                    "content": "base64_encoded_content_here",
                    "mime_type": "application/pdf"
                }
            ],
            attributes=[
                {"name": "document_type", "description": "type of document"},
                {"name": "summary", "description": "brief summary"}
            ]
        )
    """
    if not STATE_MACHINE_ARN:
        raise Exception("STATE_MACHINE_ARN not configured. Please check deployment configuration.")

    if not BUCKET_NAME:
        raise Exception("S3 bucket not configured. Cannot upload files.")

    if few_shots is None:
        few_shots = []

    if model_params is None:
        model_params = {
            "model_id": "us.anthropic.claude-3-haiku-20240307-v1:0",
            "output_length": 2000,
            "temperature": 0.0,
        }

    try:
        import base64

        uploaded_files = []
        upload_info = []

        # Upload each file to S3
        for file_data in files:
            file_name = file_data.get("name", "unnamed_file")
            file_content = file_data.get("content", "")

            if not file_content:
                raise Exception(f"No content provided for file: {file_name}")

            # Decode base64 content
            try:
                decoded_content = base64.b64decode(file_content)
            except Exception as e:
                raise Exception(f"Failed to decode base64 content for {file_name}: {str(e)}") from e

            # Generate unique S3 key
            file_path = Path(file_name)
            file_extension = file_path.suffix
            unique_id = str(uuid.uuid4())[:8]
            s3_key = f"uploaded/{file_path.stem}_{unique_id}{file_extension}"

            # Upload to S3
            try:
                s3_client.put_object(
                    Bucket=BUCKET_NAME,
                    Key=s3_key,
                    Body=decoded_content,
                    ContentType=file_data.get("mime_type", "application/octet-stream"),
                )

                uploaded_files.append(s3_key)
                upload_info.append(f"Uploaded {file_name} → s3://{BUCKET_NAME}/{s3_key}")
                print(f"📤 Uploaded {file_name} to s3://{BUCKET_NAME}/{s3_key}")

            except Exception as e:
                raise Exception(f"Failed to upload {file_name} to S3: {str(e)}") from e

        # Process uploaded files
        results = run_idp_bedrock_api(
            state_machine_arn=STATE_MACHINE_ARN,
            documents=uploaded_files,
            attributes=attributes,
            parsing_mode=parsing_mode,
            instructions=instructions,
            few_shots=few_shots,
            model_params=model_params,
        )

        return {
            "success": True,
            "results": results,
            "processed_files": len(files),
            "extracted_attributes": [attr["name"] for attr in attributes],
            "upload_info": upload_info,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "processed_files": 0, "extracted_attributes": [], "upload_info": []}


@mcp.tool()
def get_bucket_info() -> Dict[str, Any]:
    """
    Get information about the S3 bucket used for document storage.

    Returns:
        Dict containing bucket name and usage instructions
    """
    return {
        "bucket_name": BUCKET_NAME or "Not configured",
        "usage": (
            "Upload documents to this S3 bucket before processing, "
            "or use upload_and_extract_attributes for direct file upload"
        ),
        "supported_formats": [
            "Text files: .txt",
            "PDF files: .pdf",
            "Images: .jpg, .jpeg, .png",
            "Office files: .doc, .docx, .ppt, .pptx, .xls, .xlsx",
            "Web files: .html, .htm, .md, .csv",
        ],
        "direct_upload": "Use upload_and_extract_attributes tool to upload files directly via HTTP",
    }


# Note: Health check endpoint removed - FastMCP doesn't support @mcp.get() decorator
# The MCP server health can be checked by listing tools via MCP protocol

if __name__ == "__main__":
    print("🚀 Starting Tabulate MCP Server...")
    print("📋 Configuration:")
    print(f"   State Machine ARN: {STATE_MACHINE_ARN}")
    print(f"   S3 Bucket: {BUCKET_NAME}")
    print(f"   Supported Models: {len(SUPPORTED_MODELS)}")
    print(
        f"   Environment Variables Set: STATE_MACHINE_ARN={bool(os.getenv('STATE_MACHINE_ARN'))}, "
        f"BUCKET_NAME={bool(os.getenv('BUCKET_NAME'))}"
    )

    mcp.run(transport="streamable-http")
