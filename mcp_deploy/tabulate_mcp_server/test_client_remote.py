"""
Remote testing client for deployed Tabulate MCP Server
Generated automatically during deployment
"""

import asyncio
import boto3
import json
import sys
from boto3.session import Session
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test_deployed_mcp_server():
    """Test the deployed MCP server"""
    boto_session = Session()
    region = boto_session.region_name

    print(f"🔍 Testing deployed Tabulate MCP Server in {region}...")
    print("=" * 60)

    try:
        # Retrieve stored configuration
        ssm_client = boto3.client('ssm', region_name=region)
        secrets_client = boto3.client('secretsmanager', region_name=region)

        # Get agent ARN
        agent_arn_response = ssm_client.get_parameter(Name='/tabulate-mcp/runtime/agent_arn')
        agent_arn = agent_arn_response['Parameter']['Value']
        print(f"✅ Retrieved Agent ARN: {agent_arn}")

        # Get credentials
        response = secrets_client.get_secret_value(SecretId='tabulate-mcp/cognito/credentials')
        credentials = json.loads(response['SecretString'])
        bearer_token = credentials['bearer_token']
        print(f"✅ Retrieved bearer token")

    except Exception as e:
        print(f"❌ Error retrieving configuration: {e}")
        sys.exit(1)

    # Construct MCP URL
    encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    headers = {
        "authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }

    print(f"\n🔗 Connecting to: {mcp_url}")

    try:
        async with streamablehttp_client(mcp_url, headers, timeout=120, terminate_on_close=False) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                print("\n🔄 Initializing MCP session...")
                await session.initialize()
                print("✅ MCP session initialized")

                print("\n🔄 Listing available tools...")
                tool_result = await session.list_tools()

                print("\n📋 Available Tabulate MCP Tools:")
                print("=" * 50)
                for tool in tool_result.tools:
                    print(f"🔧 {tool.name}")
                    print(f"   Description: {tool.description}")
                    print()

                # Test tools
                print("🧪 Testing MCP Tools:")
                print("=" * 50)

                # Test list_supported_models
                try:
                    print("\n➡️  Testing list_supported_models...")
                    models_result = await session.call_tool(
                        name="list_supported_models",
                        arguments={}
                    )
                    print(f"   ✅ Result: {models_result.content[0].text}")
                except Exception as e:
                    print(f"   ❌ Error: {e}")

                # Test get_bucket_info
                try:
                    print("\n➡️  Testing get_bucket_info...")
                    bucket_result = await session.call_tool(
                        name="get_bucket_info",
                        arguments={}
                    )
                    print(f"   ✅ Result: {bucket_result.content[0].text}")
                except Exception as e:
                    print(f"   ❌ Error: {e}")

                print("\n🎉 Tabulate MCP Server testing completed successfully!")
                print(f"✅ Found {len(tool_result.tools)} tools available.")

    except Exception as e:
        print(f"❌ Error connecting to MCP server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_deployed_mcp_server())
