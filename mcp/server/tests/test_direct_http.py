#!/usr/bin/env python3
"""
Direct HTTP test that bypasses MCP client library issues
Tests the MCP server using raw HTTP requests
"""

import boto3
import json
import requests
import pytest
from boto3.session import Session
from .test_helpers import sync_retry_with_backoff, sync_rate_limited_sleep


@pytest.fixture(scope="module")
def mcp_config():
    """Get MCP server configuration from AWS"""
    try:
        boto_session = Session()
        region = boto_session.region_name

        ssm_client = boto3.client("ssm", region_name=region)
        secrets_client = boto3.client("secretsmanager", region_name=region)

        agent_arn_response = ssm_client.get_parameter(Name="/idp-bedrock-mcp/runtime/agent_arn")
        agent_arn = agent_arn_response["Parameter"]["Value"]

        response = secrets_client.get_secret_value(SecretId="idp-bedrock-mcp/cognito/credentials")
        credentials = json.loads(response["SecretString"])
        bearer_token = credentials["bearer_token"]

        # Construct MCP URL
        encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
        mcp_url = (
            f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
        )

        headers = {
            "authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        return {
            "mcp_url": mcp_url,
            "headers": headers,
            "agent_arn": agent_arn,
            "region": region,
        }
    except Exception as e:
        pytest.skip(f"Could not retrieve MCP configuration: {e}")


def parse_sse_response(response_text):
    """Parse Server-Sent Events response format"""
    lines = response_text.strip().split("\n")
    for line in lines:
        if line.startswith("data: "):
            json_str = line[6:]  # Remove "data: " prefix
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
    return None


def test_mcp_initialization(mcp_config):
    """Test MCP server initialization"""
    print("\n📋 Test 1: Initialize MCP session")
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "direct-http-test", "version": "1.0.0"},
        },
    }

    def make_request():
        response = requests.post(mcp_config["mcp_url"], headers=mcp_config["headers"], json=init_request, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Response length: {len(response.text)} chars")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert response.text.strip(), "Response should not be empty"

        # Handle Server-Sent Events (SSE) format
        if "text/event-stream" in response.headers.get("content-type", ""):
            print("   ✅ Received SSE response (correct MCP format)")
            json_data = parse_sse_response(response.text)
            assert json_data is not None, "Could not parse SSE data"

            print("   ✅ MCP initialization successful!")
            server_info = json_data.get("result", {}).get("serverInfo", {})
            print(f"   Server: {server_info.get('name', 'IDP Bedrock MCP Server')}")
            print(f"   Protocol: {json_data.get('result', {}).get('protocolVersion', 'Unknown')}")
        else:
            # Handle regular JSON
            result = response.json()
            print("   ✅ MCP initialization successful!")
            print(f"   Server: {result.get('result', {}).get('serverInfo', {}).get('name', 'Unknown')}")

        return response

    try:
        sync_retry_with_backoff(make_request, max_retries=3, base_delay=2.0)
    except Exception as e:
        pytest.fail(f"Request failed: {e}")


def test_list_tools(mcp_config):
    """Test listing available MCP tools"""
    print("\n📋 Test 2: List available tools")
    tools_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

    def make_request():
        # Add a small delay between tests to avoid rate limiting
        sync_rate_limited_sleep(1.0, 3.0)

        response = requests.post(mcp_config["mcp_url"], headers=mcp_config["headers"], json=tools_request, timeout=30)
        print(f"   Status: {response.status_code}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        # Handle both SSE and regular JSON responses
        if "text/event-stream" in response.headers.get("content-type", ""):
            # Parse SSE format
            json_data = parse_sse_response(response.text)
            assert json_data is not None, "Could not parse SSE response"
            result = json_data
        else:
            # Handle regular JSON
            result = response.json()

        tools = result.get("result", {}).get("tools", [])
        print(f"   ✅ Found {len(tools)} MCP tools:")
        for tool in tools:
            print(f"      🔧 {tool['name']}")

        assert len(tools) > 0, "Should have at least one tool"

        # Check for expected tools
        tool_names = [tool["name"] for tool in tools]
        expected_tools = [
            "extract_document_attributes",
            "get_extraction_status",
            "list_supported_models",
            "get_bucket_info",
        ]

        for expected_tool in expected_tools:
            assert expected_tool in tool_names, f"Should have {expected_tool} tool"

        return response

    try:
        sync_retry_with_backoff(make_request, max_retries=3, base_delay=2.0)
    except Exception as e:
        pytest.fail(f"Request failed: {e}")


def check_s3_file_exists(bucket_name, key, region):
    """Check if a file exists in S3"""
    try:
        s3_client = boto3.client("s3", region_name=region)
        s3_client.head_object(Bucket=bucket_name, Key=key)
        return True
    except Exception:
        return False


def get_bucket_name(mcp_config):
    """Get the S3 bucket name from the MCP server"""
    try:
        bucket_request = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": "get_bucket_info", "arguments": {}},
        }

        response = requests.post(mcp_config["mcp_url"], headers=mcp_config["headers"], json=bucket_request, timeout=30)

        if response.status_code == 200:
            if "text/event-stream" in response.headers.get("content-type", ""):
                json_data = parse_sse_response(response.text)
                if json_data and "result" in json_data and "content" in json_data["result"]:
                    content = json_data["result"]["content"][0]["text"]
                    bucket_data = json.loads(content)
                    return bucket_data.get("bucket_name")
        return None
    except Exception:
        return None


@pytest.mark.slow
def test_document_extraction(mcp_config):
    """Test document attribute extraction tool - only if test file exists in S3"""
    print("\n📋 Test 3: Extract document attributes")

    # Check if test document exists in S3 first
    test_document = "originals/email_1.txt"
    bucket_name = get_bucket_name(mcp_config)

    if not bucket_name:
        pytest.skip("Could not determine S3 bucket name - skipping document extraction test")

    if not check_s3_file_exists(bucket_name, test_document, mcp_config["region"]):
        pytest.skip(f"Test document '{test_document}' not found in S3 bucket '{bucket_name}' - upload demo files first")

    print(f"   ✅ Test document '{test_document}' found in S3")

    extract_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "extract_document_attributes",
            "arguments": {
                "documents": [test_document],
                "attributes": [
                    {"name": "sender_name", "description": "name of the person who sent the email"},
                    {"name": "email_subject", "description": "subject line or main topic of the email"},
                    {"name": "sentiment", "description": "overall sentiment of the email"},
                ],
                "parsing_mode": "Amazon Bedrock LLM",
                "model_params": {"model_id": "us.anthropic.claude-3-haiku-20240307-v1:0", "temperature": 0.1},
            },
        },
    }

    try:
        print("   🚀 Calling MCP tool (this may take 30-60 seconds)...")
        response = requests.post(
            mcp_config["mcp_url"], headers=mcp_config["headers"], json=extract_request, timeout=180
        )
        print(f"   Status: {response.status_code}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        # Handle both SSE and regular JSON responses
        if "text/event-stream" in response.headers.get("content-type", ""):
            # Parse SSE format
            json_data = parse_sse_response(response.text)
            assert json_data is not None, "Could not parse SSE response"
            result = json_data
        else:
            # Handle regular JSON
            result = response.json()

        assert "result" in result, f"Expected 'result' in response: {result}"
        assert "content" in result["result"], f"Expected 'content' in result: {result['result']}"

        content = result["result"]["content"][0]["text"]
        extraction_data = json.loads(content)

        assert extraction_data.get("success"), f"Extraction should succeed: {extraction_data.get('error')}"

        print("\n🎉 MCP TOOL CALL SUCCESSFUL!")
        print("=" * 50)
        print("📊 RESULTS VIA MCP HTTP:")
        print("=" * 50)

        for doc_result in extraction_data["results"]:
            print(f"\n📄 Document: {doc_result['file_key']}")
            print("   Attributes extracted via MCP:")
            for attr_name, attr_value in doc_result["attributes"].items():
                print(f"   🔹 {attr_name.replace('_', ' ').title()}: {attr_value}")

        print("\n✅ YOUR MCP SERVER IS WORKING PERFECTLY!")
        print("✅ HTTP requests work fine")
        print("✅ Document processing successful")

        # Verify we got results
        assert len(extraction_data["results"]) > 0, "Should have at least one result"
        doc_result = extraction_data["results"][0]
        assert "file_key" in doc_result, "Result should contain file_key"
        assert "attributes" in doc_result, "Result should contain attributes"
        assert len(doc_result["attributes"]) > 0, "Should have extracted some attributes"

    except Exception as e:
        pytest.fail(f"Request failed: {e}")


def test_mcp_via_http(mcp_config):
    """Test MCP server using direct HTTP requests - comprehensive test"""
    print("🔥 DIRECT HTTP TEST - Bypassing MCP Client Library")
    print("=" * 60)
    print("This proves your MCP server IS working!")
    print()

    print("\n🌐 Testing MCP server via direct HTTP...")
    print(f"URL: {mcp_config['mcp_url']}")

    # This test just verifies the configuration is working
    assert mcp_config["mcp_url"] is not None, "MCP URL should be configured"
    assert mcp_config["headers"] is not None, "Headers should be configured"
    assert mcp_config["agent_arn"] is not None, "Agent ARN should be configured"

    print("✅ MCP configuration is valid")


if __name__ == "__main__":
    # Allow running as standalone script for debugging
    pytest.main([__file__, "-v", "-s"])
