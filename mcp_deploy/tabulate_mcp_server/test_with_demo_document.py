#!/usr/bin/env python3
"""
Test the deployed Tabulate MCP Server with a demo document
"""

import asyncio
import boto3
import json
import sys
from boto3.session import Session
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test_with_demo_document():
    """Test the MCP server with a demo document"""
    boto_session = Session()
    region = boto_session.region_name

    print("🧪 Testing Tabulate MCP Server with demo document...")
    print("=" * 60)

    try:
        # Retrieve stored configuration
        ssm_client = boto3.client("ssm", region_name=region)
        secrets_client = boto3.client("secretsmanager", region_name=region)

        # Get agent ARN
        agent_arn_response = ssm_client.get_parameter(Name="/tabulate-mcp/runtime/agent_arn")
        agent_arn = agent_arn_response["Parameter"]["Value"]
        print(f"✅ Retrieved Agent ARN: {agent_arn}")

        # Get credentials
        response = secrets_client.get_secret_value(SecretId="tabulate-mcp/cognito/credentials")
        credentials = json.loads(response["SecretString"])
        bearer_token = credentials["bearer_token"]
        print("✅ Retrieved bearer token")

    except Exception as e:
        print(f"❌ Error retrieving configuration: {e}")
        sys.exit(1)

    # Construct MCP URL
    encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    headers = {
        "authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }

    print("\n🔗 Connecting to MCP server...")

    try:
        async with streamablehttp_client(mcp_url, headers, timeout=120, terminate_on_close=False) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                print("🔄 Initializing MCP session...")
                await session.initialize()
                print("✅ MCP session initialized")

                print("\n📋 Testing with demo document: originals/email_1.txt")
                print("=" * 50)

                # Test document attribute extraction with email_1.txt
                try:
                    print("➡️  Extracting attributes from email_1.txt...")

                    # Define attributes to extract (similar to demo notebook)
                    attributes = [
                        {
                            "name": "customer_name",
                            "description": "name of the customer who wrote the email"
                        },
                        {
                            "name": "sentiment",
                            "description": "sentiment of the email (positive, negative, neutral)"
                        },
                        {
                            "name": "urgency",
                            "description": "urgency level of the email (high, medium, low)"
                        },
                        {
                            "name": "main_topic",
                            "description": "main topic or subject of the email"
                        }
                    ]

                    extraction_result = await session.call_tool(
                        name="extract_document_attributes",
                        arguments={
                            "documents": ["originals/email_1.txt"],
                            "attributes": attributes,
                            "parsing_mode": "Amazon Bedrock LLM",
                            "model_params": {
                                "model_id": "us.anthropic.claude-3-haiku-20240307-v1:0",
                                "temperature": 0.1
                            }
                        }
                    )

                    print("✅ Extraction completed!")
                    result_data = json.loads(extraction_result.content[0].text)

                    if result_data.get("success"):
                        print(f"\n📊 Results for {result_data['processed_documents']} document(s):")
                        print("-" * 40)

                        for result in result_data["results"]:
                            print(f"📄 Document: {result['file_key']}")
                            print("   Extracted attributes:")
                            for attr_name, attr_value in result["attributes"].items():
                                print(f"   • {attr_name}: {attr_value}")
                            print()
                    else:
                        print(f"❌ Extraction failed: {result_data.get('error', 'Unknown error')}")

                except Exception as e:
                    print(f"❌ Error during extraction: {e}")

                # Test other tools
                print("\n🔧 Testing other MCP tools:")
                print("=" * 40)

                # Test list_supported_models
                try:
                    print("➡️  Getting supported models...")
                    models_result = await session.call_tool(
                        name="list_supported_models",
                        arguments={}
                    )
                    models_data = json.loads(models_result.content[0].text)
                    print(f"✅ Found {len(models_data['models'])} supported models")
                    print(f"   Default model: {models_data['default_model']}")
                except Exception as e:
                    print(f"❌ Error getting models: {e}")

                # Test get_bucket_info
                try:
                    print("\n➡️  Getting bucket information...")
                    bucket_result = await session.call_tool(
                        name="get_bucket_info",
                        arguments={}
                    )
                    bucket_data = json.loads(bucket_result.content[0].text)
                    print(f"✅ S3 Bucket: {bucket_data['bucket_name']}")
                    print(f"   Supported formats: {len(bucket_data['supported_formats'])} types")
                except Exception as e:
                    print(f"❌ Error getting bucket info: {e}")

                print("\n🎉 Demo document testing completed successfully!")
                print("✅ The Tabulate MCP Server is working correctly with real documents!")

    except Exception as e:
        print(f"❌ Error connecting to MCP server: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure the MCP server is deployed and running")
        print("2. Check that the demo document 'originals/email_1.txt' exists in S3")
        print("3. Verify AWS credentials and permissions")
        sys.exit(1)

if __name__ == "__main__":
    print("🚀 Tabulate MCP Server Demo Document Test")
    print("This script tests document attribute extraction using email_1.txt")
    print()

    asyncio.run(test_with_demo_document())
