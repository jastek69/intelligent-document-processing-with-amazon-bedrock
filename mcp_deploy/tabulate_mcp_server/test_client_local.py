"""
Local testing client for Tabulate MCP Server
"""

import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def test_local_mcp_server():
    """Test the locally running MCP server"""
    mcp_url = "http://localhost:8000/mcp"
    headers = {}

    print("🔄 Connecting to local MCP server...")
    print(f"URL: {mcp_url}")

    try:
        async with streamablehttp_client(mcp_url, headers, timeout=120, terminate_on_close=False) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                print("✅ Connected to MCP server")
                
                # Initialize session
                print("\n🔄 Initializing MCP session...")
                await session.initialize()
                print("✅ MCP session initialized")
                
                # List available tools
                print("\n🔄 Listing available tools...")
                tool_result = await session.list_tools()
                
                print("\n📋 Available MCP Tools:")
                print("=" * 60)
                for tool in tool_result.tools:
                    print(f"🔧 {tool.name}")
                    print(f"   Description: {tool.description}")
                    if hasattr(tool, 'inputSchema') and tool.inputSchema:
                        properties = tool.inputSchema.get('properties', {})
                        if properties:
                            print(f"   Parameters: {list(properties.keys())}")
                    print()
                
                print(f"✅ Found {len(tool_result.tools)} tools available")
                
                # Test list_supported_models tool
                print("\n🧪 Testing list_supported_models tool...")
                try:
                    models_result = await session.call_tool(
                        name="list_supported_models",
                        arguments={}
                    )
                    print("✅ Models tool result:")
                    print(f"   {models_result.content[0].text}")
                except Exception as e:
                    print(f"❌ Error testing models tool: {e}")
                
                # Test get_bucket_info tool
                print("\n🧪 Testing get_bucket_info tool...")
                try:
                    bucket_result = await session.call_tool(
                        name="get_bucket_info",
                        arguments={}
                    )
                    print("✅ Bucket info tool result:")
                    print(f"   {bucket_result.content[0].text}")
                except Exception as e:
                    print(f"❌ Error testing bucket info tool: {e}")
                
                # Test extract_document_attributes tool (will fail without proper config)
                print("\n🧪 Testing extract_document_attributes tool...")
                try:
                    extract_result = await session.call_tool(
                        name="extract_document_attributes",
                        arguments={
                            "documents": ["test/sample.txt"],
                            "attributes": [
                                {"name": "test_attr", "description": "test attribute"}
                            ]
                        }
                    )
                    print("✅ Extract tool result:")
                    print(f"   {extract_result.content[0].text}")
                except Exception as e:
                    print(f"⚠️  Extract tool error (expected without config): {e}")
                
                print("\n✅ Local MCP server testing completed!")
                
    except Exception as e:
        print(f"❌ Error connecting to MCP server: {e}")
        print("Make sure the MCP server is running with: python mcp_server.py")

if __name__ == "__main__":
    asyncio.run(test_local_mcp_server())
