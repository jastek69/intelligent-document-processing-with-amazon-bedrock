"""
Tabulate MCP Server - Exposes document attribute extraction via MCP protocol
"""

import json
import time
import boto3
import os
from typing import Any, Dict, List, Optional, Sequence, Union
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

# Initialize MCP server with stateless HTTP for AgentCore Runtime compatibility
mcp = FastMCP(host="0.0.0.0", stateless_http=True)

# Initialize AWS clients
stepfunctions_client = boto3.client("stepfunctions")

# Get configuration dynamically
def get_configuration():
    """Get configuration from environment variables or AWS discovery"""
    state_machine_arn = os.getenv("STATE_MACHINE_ARN")
    bucket_name = os.getenv("BUCKET_NAME")
    
    # If environment variables are not set, try to discover from AWS
    if not state_machine_arn or not bucket_name:
        print("⚠️  Environment variables not set, attempting AWS discovery...")
        try:
            # Try to discover infrastructure
            boto_session = boto3.Session()
            region = boto_session.region_name
            account_id = boto3.client("sts").get_caller_identity()["Account"]
            
            if not state_machine_arn:
                # Try to find Step Functions state machine
                sf_client = boto3.client('stepfunctions', region_name=region)
                try:
                    paginator = sf_client.get_paginator('list_state_machines')
                    for page in paginator.paginate():
                        for sm in page['stateMachines']:
                            if 'idp-bedrock' in sm['name'].lower():
                                state_machine_arn = sm['stateMachineArn']
                                print(f"✅ Discovered Step Functions: {state_machine_arn}")
                                break
                        if state_machine_arn:
                            break
                except Exception as e:
                    print(f"⚠️  Could not discover Step Functions: {e}")
            
            if not bucket_name:
                # Try to find S3 bucket
                s3_client = boto3.client('s3', region_name=region)
                try:
                    response = s3_client.list_buckets()
                    for bucket in response['Buckets']:
                        if 'idp-bedrock' in bucket['Name'].lower() and 'data' in bucket['Name'].lower():
                            bucket_name = bucket['Name']
                            print(f"✅ Discovered S3 bucket: {bucket_name}")
                            break
                except Exception as e:
                    print(f"⚠️  Could not discover S3 bucket: {e}")
            
            # Fallback to expected naming patterns
            if not state_machine_arn:
                state_machine_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:idp-bedrock-StepFunctions"
                print(f"⚠️  Using fallback Step Functions ARN: {state_machine_arn}")
            
            if not bucket_name:
                bucket_name = f"idp-bedrock-data-{account_id}"
                print(f"⚠️  Using fallback bucket name: {bucket_name}")
                
        except Exception as e:
            print(f"❌ Error during AWS discovery: {e}")
            # Use hardcoded fallbacks as last resort
            state_machine_arn = "arn:aws:states:us-east-1:471112811980:stateMachine:idp-bedrock-StepFunctions"
            bucket_name = "idp-bedrock-data-471112811980"
            print(f"⚠️  Using hardcoded fallbacks")
    
    return state_machine_arn, bucket_name

# Get configuration
STATE_MACHINE_ARN, BUCKET_NAME = get_configuration()

SUPPORTED_MODELS = [
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0", 
    "us.anthropic.claude-3-haiku-20240307-v1:0",
    "us.amazon.nova-premier-v1:0",
    "us.amazon.nova-pro-v1:0",
    "us.amazon.nova-lite-v1:0"
]

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
            "temperature": 0.0
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
                    {
                        "file_key": output["llm_answer"]["file_key"], 
                        "attributes": output["llm_answer"]["answer"]
                    }
                )
            return results

@mcp.tool()
def extract_document_attributes(
    documents: List[str],
    attributes: List[Dict[str, Any]],
    parsing_mode: str = "Amazon Textract",
    instructions: str = "",
    few_shots: List[Dict[str, Any]] = None,
    model_params: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Extract custom attributes from documents using Amazon Bedrock and AWS document processing services.
    
    This tool processes documents (text, PDF, images, Office files) and extracts specified attributes
    using large language models. It supports various parsing modes and can handle batch processing.
    
    Args:
        documents: List of document paths/keys in S3 (e.g., ["originals/email_1.txt", "originals/doc.pdf"])
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
            "temperature": 0.0
        }
    
    try:
        results = run_idp_bedrock_api(
            state_machine_arn=STATE_MACHINE_ARN,
            documents=documents,
            attributes=attributes,
            parsing_mode=parsing_mode,
            instructions=instructions,
            few_shots=few_shots,
            model_params=model_params
        )
        
        return {
            "success": True,
            "results": results,
            "processed_documents": len(documents),
            "extracted_attributes": [attr["name"] for attr in attributes]
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "processed_documents": 0,
            "extracted_attributes": []
        }

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
        
        result = {
            "status": status,
            "execution_arn": execution_arn
        }
        
        if status == "SUCCEEDED":
            outputs = json.loads(response["output"])
            results = []
            for output in outputs:
                results.append(
                    {
                        "file_key": output["llm_answer"]["file_key"],
                        "attributes": output["llm_answer"]["answer"]
                    }
                )
            result["results"] = results
            
        elif status == "FAILED":
            result["error"] = response.get("error", "Unknown error")
            
        return result
        
    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "execution_arn": execution_arn
        }

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
            "recommended_for_quality": "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        }
    }

@mcp.tool()
def get_bucket_info() -> Dict[str, Any]:
    """
    Get information about the S3 bucket used for document storage.
    
    Returns:
        Dict containing bucket name and usage instructions
    """
    return {
        "bucket_name": BUCKET_NAME or "Not configured",
        "usage": "Upload documents to this S3 bucket before processing",
        "supported_formats": [
            "Text files: .txt",
            "PDF files: .pdf", 
            "Images: .jpg, .jpeg, .png",
            "Office files: .doc, .docx, .ppt, .pptx, .xls, .xlsx",
            "Web files: .html, .htm, .md, .csv"
        ]
    }

# Note: Health check endpoint removed - FastMCP doesn't support @mcp.get() decorator
# The MCP server health can be checked by listing tools via MCP protocol

if __name__ == "__main__":
    print(f"🚀 Starting Tabulate MCP Server...")
    print(f"📋 Configuration:")
    print(f"   State Machine ARN: {STATE_MACHINE_ARN}")
    print(f"   S3 Bucket: {BUCKET_NAME}")
    print(f"   Supported Models: {len(SUPPORTED_MODELS)}")
    print(f"   Environment Variables Set: STATE_MACHINE_ARN={bool(os.getenv('STATE_MACHINE_ARN'))}, BUCKET_NAME={bool(os.getenv('BUCKET_NAME'))}")
    
    mcp.run(transport="streamable-http")
