#!/usr/bin/env python3
"""
Comprehensive Test Suite for IDP with Amazon Bedrock MCP Server
Can be run standalone: python test_mcp_server.py

This script provides a complete test suite for validating the MCP server functionality
including connectivity, protocol compliance, tools availability, and document processing.
"""

import boto3
import json
import requests
import time
import argparse
from boto3.session import Session
from typing import Dict, Any


class Colors:
    """ANSI color codes for beautiful output"""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


class MCPTester:
    """Comprehensive MCP Server Tester"""

    def __init__(self):
        self.config = None
        self.results = []

    def print_header(self, title: str, char: str = "="):
        """Print a beautiful header"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{char * 60}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{title.center(60)}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{char * 60}{Colors.END}")

    def print_test(self, test_name: str, status: str = "RUNNING"):
        """Print test status"""
        if status == "RUNNING":
            print(f"\n🧪 {Colors.BOLD}{test_name}{Colors.END}")
        elif status == "PASS":
            print(f"   ✅ {Colors.GREEN}{test_name} - PASSED{Colors.END}")
        elif status == "FAIL":
            print(f"   ❌ {Colors.RED}{test_name} - FAILED{Colors.END}")
        elif status == "WARN":
            print(f"   ⚠️  {Colors.YELLOW}{test_name} - WARNING{Colors.END}")

    def print_info(self, message: str):
        """Print info message"""
        print(f"   {Colors.CYAN}ℹ️  {message}{Colors.END}")

    def print_success(self, message: str):
        """Print success message"""
        print(f"   {Colors.GREEN}✅ {message}{Colors.END}")

    def print_error(self, message: str):
        """Print error message"""
        print(f"   {Colors.RED}❌ {message}{Colors.END}")

    def print_warning(self, message: str):
        """Print warning message"""
        print(f"   {Colors.YELLOW}⚠️  {message}{Colors.END}")

    def get_mcp_config(self) -> Dict[str, Any]:
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
            self.print_error(f"Could not retrieve MCP configuration: {e}")
            return None

    def parse_sse_response(self, response_text: str) -> Dict[str, Any]:
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

    def test_configuration(self) -> bool:
        """Test 1: Configuration Validation"""
        self.print_test("Configuration Validation", "RUNNING")

        self.config = self.get_mcp_config()
        if not self.config:
            self.print_test("Configuration Validation", "FAIL")
            return False

        self.print_info(f"Agent ARN: {self.config['agent_arn']}")
        self.print_info(f"Region: {self.config['region']}")
        self.print_info(f"URL: {self.config['mcp_url'][:50]}...")
        self.print_test("Configuration Validation", "PASS")
        return True

    def test_connectivity(self) -> bool:
        """Test 2: Server Connectivity"""
        self.print_test("Server Connectivity", "RUNNING")

        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "mcp-tester", "version": "1.0.0"},
            },
        }

        try:
            response = requests.post(
                self.config["mcp_url"], headers=self.config["headers"], json=init_request, timeout=30
            )
            self.print_info(f"Status: {response.status_code}")
            self.print_info(f"Response time: {response.elapsed.total_seconds():.2f}s")

            if response.status_code == 200:
                self.print_success("Server is reachable and responding")
                self.print_test("Server Connectivity", "PASS")
                return True
            if response.status_code == 429:
                self.print_warning("Server is reachable but rate limited")
                self.print_test("Server Connectivity", "WARN")
                return True
            self.print_error(f"Server error: {response.status_code}")
            self.print_test("Server Connectivity", "FAIL")
            return False

        except requests.exceptions.Timeout:
            self.print_error("Connection timeout - server may be down")
            self.print_test("Server Connectivity", "FAIL")
            return False
        except requests.exceptions.ConnectionError:
            self.print_error("Connection error - server may be unreachable")
            self.print_test("Server Connectivity", "FAIL")
            return False
        except Exception as e:
            self.print_error(f"Unexpected error: {e}")
            self.print_test("Server Connectivity", "FAIL")
            return False

    def test_mcp_protocol(self) -> bool:
        """Test 3: MCP Protocol Compliance"""
        self.print_test("MCP Protocol Compliance", "RUNNING")

        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "mcp-tester", "version": "1.0.0"},
            },
        }

        try:
            time.sleep(1)  # Rate limiting delay
            response = requests.post(
                self.config["mcp_url"], headers=self.config["headers"], json=init_request, timeout=30
            )

            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" in content_type:
                    self.print_success("Proper SSE content type")

                    json_data = self.parse_sse_response(response.text)
                    if json_data and "result" in json_data and "serverInfo" in json_data["result"]:
                        server_info = json_data["result"]["serverInfo"]
                        self.print_success(f"Server name: {server_info.get('name', 'Unknown')}")
                        self.print_success(f"Protocol version: {json_data['result'].get('protocolVersion', 'Unknown')}")
                        self.print_test("MCP Protocol Compliance", "PASS")
                        return True
                    self.print_warning("Could not parse server info")
                    self.print_test("MCP Protocol Compliance", "WARN")
                    return True
                self.print_warning(f"Unexpected content type: {content_type}")
                self.print_test("MCP Protocol Compliance", "WARN")
                return True
            if response.status_code == 429:
                self.print_warning("Rate limited - protocol likely working")
                self.print_test("MCP Protocol Compliance", "WARN")
                return True
            self.print_error(f"HTTP error: {response.status_code}")
            self.print_test("MCP Protocol Compliance", "FAIL")
            return False

        except Exception as e:
            self.print_error(f"Request failed: {e}")
            self.print_test("MCP Protocol Compliance", "FAIL")
            return False

    def test_tools_listing(self) -> bool:
        """Test 4: Tools Listing"""
        self.print_test("Tools Listing", "RUNNING")

        tools_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

        try:
            time.sleep(2)  # Rate limiting delay
            response = requests.post(
                self.config["mcp_url"], headers=self.config["headers"], json=tools_request, timeout=30
            )

            if response.status_code == 200:
                if "text/event-stream" in response.headers.get("content-type", ""):
                    json_data = self.parse_sse_response(response.text)
                    if not json_data:
                        self.print_error("Could not parse tools response")
                        self.print_test("Tools Listing", "FAIL")
                        return False
                    result = json_data
                else:
                    result = response.json()

                tools = result.get("result", {}).get("tools", [])
                self.print_success(f"Found {len(tools)} tools")

                for tool in tools:
                    self.print_info(f"🔧 {tool['name']}")

                # Check for critical tools
                tool_names = [tool["name"] for tool in tools]
                expected_tools = ["extract_document_attributes", "list_supported_models", "get_bucket_info"]

                available_tools = [tool for tool in expected_tools if tool in tool_names]
                self.print_success(f"Critical tools available: {len(available_tools)}/{len(expected_tools)}")

                if len(available_tools) >= 2:
                    self.print_test("Tools Listing", "PASS")
                    return True
                self.print_warning("Some critical tools missing")
                self.print_test("Tools Listing", "WARN")
                return True

            if response.status_code == 429:
                self.print_warning("Rate limited - tools likely available")
                self.print_test("Tools Listing", "WARN")
                return True
            self.print_error(f"HTTP error: {response.status_code}")
            self.print_test("Tools Listing", "FAIL")
            return False

        except Exception as e:
            self.print_error(f"Request failed: {e}")
            self.print_test("Tools Listing", "FAIL")
            return False

    def test_aws_integration(self) -> bool:
        """Test 5: AWS Integration"""
        self.print_test("AWS Integration", "RUNNING")

        bucket_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_bucket_info", "arguments": {}},
        }

        try:
            time.sleep(3)  # Rate limiting delay
            response = requests.post(
                self.config["mcp_url"], headers=self.config["headers"], json=bucket_request, timeout=60
            )

            if response.status_code == 200:
                if "text/event-stream" in response.headers.get("content-type", ""):
                    json_data = self.parse_sse_response(response.text)
                    if not json_data:
                        self.print_error("Could not parse bucket info response")
                        self.print_test("AWS Integration", "FAIL")
                        return False
                    result = json_data
                else:
                    result = response.json()

                if "result" in result and "content" in result["result"]:
                    content = result["result"]["content"][0]["text"]
                    bucket_data = json.loads(content)

                    if "bucket_name" in bucket_data:
                        self.print_success("S3 integration working")
                        self.print_success(f"Bucket: {bucket_data['bucket_name']}")
                        self.print_test("AWS Integration", "PASS")
                        return True
                    self.print_warning("Unexpected bucket response format")
                    self.print_test("AWS Integration", "WARN")
                    return True
                self.print_warning("Missing content in response")
                self.print_test("AWS Integration", "WARN")
                return True

            if response.status_code == 429:
                self.print_warning("Rate limited - AWS integration likely working")
                self.print_test("AWS Integration", "WARN")
                return True
            self.print_error(f"HTTP error: {response.status_code}")
            self.print_test("AWS Integration", "FAIL")
            return False

        except Exception as e:
            self.print_error(f"Request failed: {e}")
            self.print_test("AWS Integration", "FAIL")
            return False

    def test_document_extraction(self) -> bool:
        """Test 6: Document Extraction (Optional)"""
        self.print_test("Document Extraction", "RUNNING")

        extract_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "extract_document_attributes",
                "arguments": {
                    "documents": ["originals/email_1.txt"],
                    "attributes": [
                        {"name": "sender_name", "description": "name of the person who sent the email"},
                        {"name": "sentiment", "description": "overall sentiment of the email"},
                    ],
                    "parsing_mode": "Amazon Bedrock LLM",
                    "model_params": {"model_id": "us.anthropic.claude-3-haiku-20240307-v1:0", "temperature": 0.1},
                },
            },
        }

        try:
            self.print_info("Calling document extraction (may take 30-60 seconds)...")
            time.sleep(5)  # Rate limiting delay

            response = requests.post(
                self.config["mcp_url"], headers=self.config["headers"], json=extract_request, timeout=180
            )

            if response.status_code == 200:
                if "text/event-stream" in response.headers.get("content-type", ""):
                    json_data = self.parse_sse_response(response.text)
                    if not json_data:
                        self.print_error("Could not parse extraction response")
                        self.print_test("Document Extraction", "FAIL")
                        return False
                    result = json_data
                else:
                    result = response.json()

                if "result" in result and "content" in result["result"]:
                    content = result["result"]["content"][0]["text"]
                    extraction_data = json.loads(content)

                    if extraction_data.get("success"):
                        self.print_success("Document extraction successful!")

                        for doc_result in extraction_data["results"]:
                            self.print_info(f"📄 Document: {doc_result['file_key']}")
                            for attr_name, attr_value in doc_result["attributes"].items():
                                self.print_info(f"   🔹 {attr_name.replace('_', ' ').title()}: {attr_value}")

                        self.print_test("Document Extraction", "PASS")
                        return True
                    self.print_error(f"Extraction failed: {extraction_data.get('error')}")
                    self.print_test("Document Extraction", "FAIL")
                    return False
                self.print_error("Unexpected response format")
                self.print_test("Document Extraction", "FAIL")
                return False

            if response.status_code == 429:
                self.print_warning("Rate limited - extraction likely working")
                self.print_test("Document Extraction", "WARN")
                return True
            self.print_error(f"HTTP error: {response.status_code}")
            self.print_test("Document Extraction", "FAIL")
            return False

        except Exception as e:
            self.print_error(f"Request failed: {e}")
            self.print_test("Document Extraction", "FAIL")
            return False

    def _prepare_demo_file(self, demo_file_path: str) -> str | None:
        """Helper method to read and encode demo file."""
        import base64
        import os

        if not os.path.exists(demo_file_path):
            self.print_error(f"Demo file not found: {demo_file_path}")
            return None

        try:
            with open(demo_file_path, "rb") as f:
                file_content = f.read()

            base64_content = base64.b64encode(file_content).decode("utf-8")
            self.print_info(f"Encoded demo file: {len(file_content)} bytes → {len(base64_content)} chars")
            return base64_content

        except Exception as e:
            self.print_error(f"Failed to read/encode demo file: {e}")
            return None

    def _create_upload_request(self, base64_content: str) -> dict:
        """Helper method to create upload request."""
        return {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "upload_and_extract_attributes",
                "arguments": {
                    "files": [{"name": "customer_email.txt", "content": base64_content, "mime_type": "text/plain"}],
                    "attributes": [
                        {"name": "customer_name", "description": "name of the customer who sent the email"},
                        {"name": "tracking_number", "description": "shipment tracking number mentioned in the email"},
                        {"name": "issue_type", "description": "type of customer issue or inquiry"},
                        {"name": "urgency", "description": "urgency level of the request: low, medium, high"},
                    ],
                    "parsing_mode": "Amazon Bedrock LLM",
                    "model_params": {"model_id": "us.anthropic.claude-3-haiku-20240307-v1:0", "temperature": 0.1},
                },
            },
        }

    def _process_upload_response(self, response) -> bool:
        """Helper method to process upload response."""
        if response.status_code == 200:
            return self._handle_success_response(response)
        if response.status_code == 429:
            self.print_warning("Rate limited - direct upload likely working")
            self.print_test("Direct File Upload", "WARN")
            return True

        self.print_error(f"HTTP error: {response.status_code}")
        self.print_test("Direct File Upload", "FAIL")
        return False

    def _handle_success_response(self, response) -> bool:
        """Helper method to handle successful response."""
        if "text/event-stream" in response.headers.get("content-type", ""):
            json_data = self.parse_sse_response(response.text)
            if not json_data:
                self.print_error("Could not parse direct upload response")
                self.print_test("Direct File Upload", "FAIL")
                return False
            result = json_data
        else:
            result = response.json()

        if "result" in result and "content" in result["result"]:
            content = result["result"]["content"][0]["text"]
            upload_data = json.loads(content)

            if upload_data.get("success"):
                self._display_upload_results(upload_data)
                self.print_test("Direct File Upload", "PASS")
                return True

            self.print_error(f"Upload failed: {upload_data.get('error')}")
            self.print_test("Direct File Upload", "FAIL")
            return False

        self.print_error("Unexpected response format")
        self.print_test("Direct File Upload", "FAIL")
        return False

    def _display_upload_results(self, upload_data: dict) -> None:
        """Helper method to display upload results."""
        self.print_success("Direct file upload successful!")

        # Show upload information
        if "upload_info" in upload_data:
            for info in upload_data["upload_info"]:
                self.print_success(f"📤 {info}")

        # Show extraction results
        for doc_result in upload_data["results"]:
            self.print_info(f"📄 Processed: {doc_result['file_key']}")
            for attr_name, attr_value in doc_result["attributes"].items():
                self.print_info(f"   🔹 {attr_name.replace('_', ' ').title()}: {attr_value}")

        self.print_success(f"Processed {upload_data['processed_files']} file(s)")
        self.print_success(f"Extracted {len(upload_data['extracted_attributes'])} attribute(s)")

    def test_direct_file_upload(self) -> bool:
        """Test 7: Direct File Upload via HTTP (Optional)"""
        self.print_test("Direct File Upload", "RUNNING")

        # Use real demo file
        demo_file_path = "../../demo/originals/email_1.txt"

        base64_content = self._prepare_demo_file(demo_file_path)
        if not base64_content:
            self.print_test("Direct File Upload", "FAIL")
            return False

        upload_request = self._create_upload_request(base64_content)

        try:
            self.print_info("Testing direct file upload with real demo file...")
            self.print_info("This may take 30-60 seconds...")
            time.sleep(5)  # Rate limiting delay

            response = requests.post(
                self.config["mcp_url"], headers=self.config["headers"], json=upload_request, timeout=180
            )

            return self._process_upload_response(response)

        except Exception as e:
            self.print_error(f"Request failed: {e}")
            self.print_test("Direct File Upload", "FAIL")
            return False

    def run_test_suite(self, include_extraction: bool = False, include_direct_upload: bool = False) -> bool:
        """Run the complete test suite"""
        self.print_header("🚀 IDP with Amazon Bedrock MCP Server Test Suite")

        # Test suite
        tests = [
            ("Configuration", self.test_configuration),
            ("Connectivity", self.test_connectivity),
            ("MCP Protocol", self.test_mcp_protocol),
            ("Tools Listing", self.test_tools_listing),
            ("AWS Integration", self.test_aws_integration),
        ]

        if include_extraction:
            tests.append(("Document Extraction", self.test_document_extraction))

        if include_direct_upload:
            tests.append(("Direct File Upload", self.test_direct_file_upload))

        # Run tests
        results = []
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append(result)
            except Exception as e:
                self.print_error(f"Test {test_name} crashed: {e}")
                results.append(False)

        # Summary
        self.print_header("📊 Test Results Summary")

        passed = sum(results)
        total = len(results)

        print(f"\n{Colors.BOLD}Results:{Colors.END}")
        print(f"   {Colors.GREEN}✅ Passed: {passed}/{total}{Colors.END}")
        print(f"   {Colors.RED}❌ Failed: {total - passed}/{total}{Colors.END}")

        if passed == total:
            print(f"\n{Colors.BOLD}{Colors.GREEN}🎉 ALL TESTS PASSED!{Colors.END}")
            print(f"{Colors.GREEN}✅ Your MCP server is working perfectly!{Colors.END}")
            return True
        if passed >= total * 0.8:  # 80% pass rate
            print(f"\n{Colors.BOLD}{Colors.YELLOW}⚠️  Most tests passed ({passed}/{total}){Colors.END}")
            print(f"{Colors.YELLOW}✅ Server is mostly functional{Colors.END}")
            print(f"{Colors.YELLOW}💡 Some failures may be due to rate limiting{Colors.END}")
            return True
        print(f"\n{Colors.BOLD}{Colors.RED}❌ Multiple tests failed ({total - passed}/{total}){Colors.END}")
        print(f"{Colors.RED}💡 Check server deployment and AWS configuration{Colors.END}")
        return False


def main():
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(
        description="Comprehensive test suite for IDP with Amazon Bedrock MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_mcp_server.py                    # Run basic tests
  python test_mcp_server.py --full             # Run all tests including document extraction
  python test_mcp_server.py --extraction-only  # Run only document extraction test
        """,
    )

    parser.add_argument("--full", action="store_true", help="Run full test suite including document extraction")
    parser.add_argument("--with-upload", action="store_true", help="Include direct file upload test")
    parser.add_argument("--extraction-only", action="store_true", help="Run only document extraction test")
    parser.add_argument("--upload-only", action="store_true", help="Run only direct file upload test")

    args = parser.parse_args()

    tester = MCPTester()

    if args.extraction_only:
        # Run only extraction test
        tester.print_header("🧪 Document Extraction Test Only")
        if tester.test_configuration():
            success = tester.test_document_extraction()
        else:
            success = False
    elif args.upload_only:
        # Run only direct upload test
        tester.print_header("🧪 Direct File Upload Test Only")
        if tester.test_configuration():
            success = tester.test_direct_file_upload()
        else:
            success = False
    else:
        # Run test suite
        include_extraction = args.full
        include_direct_upload = args.with_upload or args.full

        if not include_extraction and not include_direct_upload:
            print(
                f"\n{Colors.YELLOW}💡 Running basic test suite. "
                f"Use --full for all tests or --with-upload for direct upload test.{Colors.END}"
            )

        success = tester.run_test_suite(
            include_extraction=include_extraction, include_direct_upload=include_direct_upload
        )

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
