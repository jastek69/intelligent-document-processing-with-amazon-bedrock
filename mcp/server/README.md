# IDP with Amazon Bedrock MCP Server

This directory contains the implementation and deployment scripts for the IDP with Amazon Bedrock MCP Server, which exposes the document attribute extraction functionality as MCP (Model Context Protocol) tools.

## Overview

The IDP with Amazon Bedrock MCP Server transforms the existing IDP project into an MCP-compatible service that can be used by any MCP client or AI agent. It provides a standardized interface for document attribute extraction while leveraging the existing AWS infrastructure.

## Key Features

- **🔄 Reuses Existing Infrastructure**: Leverages deployed Step Functions, S3 bucket, and Cognito user pool
- **🛡️ Secure Authentication**: Integrates with existing Cognito authentication
- **📋 MCP-Compliant**: Provides standardized MCP tools for document processing
- **☁️ Fully Managed**: Hosted on Amazon Bedrock AgentCore Runtime with automatic scaling
- **🧪 Testing Support**: Includes comprehensive test suite with pytest

## MCP Tools Provided

### 1. `extract_document_attributes`
Main tool for document attribute extraction from various document types.

**Parameters:**
- `documents`: List of document paths/keys in S3
- `attributes`: List of attribute definitions to extract
- `parsing_mode`: "Amazon Textract", "Amazon Bedrock LLM", or "Bedrock Data Automation"
- `instructions`: Optional high-level instructions
- `few_shots`: Optional example input/output pairs
- `model_params`: Model configuration (model_id, temperature, etc.)

**Example:**
```python
{
    "documents": ["originals/email_1.txt"],
    "attributes": [
        {"name": "customer_name", "description": "name of the customer who wrote the email"},
        {"name": "sentiment", "description": "sentiment score between 0 and 1"}
    ]
}
```

### 2. `get_extraction_status`
Check the status of long-running extraction operations.

**Parameters:**
- `execution_arn`: The ARN of the Step Functions execution to check

### 3. `list_supported_models`
Get the list of supported Amazon Bedrock models.

**Returns:**
- List of available model IDs
- Default model information
- Model recommendations

### 4. `get_bucket_info`
Information about the S3 bucket and supported document formats.

**Returns:**
- Bucket name
- Supported file formats
- Usage instructions

## Files Structure

```
mcp/server/
├── README.md                      # This file
├── mcp_server.py                  # Main MCP server implementation
├── requirements.txt               # Python dependencies
├── utils.py                       # Utility functions for deployment
├── deploy_idp_bedrock_mcp.ipynb      # Main deployment notebook
├── deploy_idp_bedrock_mcp.py         # Deployment script
├── example_usage.py               # Usage examples
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── pytest.ini                # Pytest configuration
│   ├── test_direct_http.py        # Direct HTTP API tests
│   ├── test_client_remote.py      # Remote client tests
│   ├── test_with_demo_document.py # Document processing tests
│   └── test_*.py                  # Additional test files
└── config files...                # Various configuration files
```

## Prerequisites

Before deploying the IDP with Amazon Bedrock MCP Server, ensure you have:

1. **IDP Project Deployed**: The main IDP project must be deployed with:
   - Step Functions state machine
   - S3 bucket for document storage
   - Cognito user pool for authentication
   - All Lambda functions operational

2. **AWS Credentials**: Properly configured AWS credentials with permissions for:
   - Amazon Bedrock AgentCore
   - IAM role creation
   - Systems Manager Parameter Store
   - AWS Secrets Manager
   - Amazon ECR

3. **Development Environment**:
   - Python 3.10+
   - Docker running
   - Jupyter notebook environment

## Deployment

### Step 1: Navigate to Directory
```bash
cd mcp/server/
```

### Step 2: Run Deployment Notebook
Open and run the deployment notebook:
```bash
jupyter notebook deploy_tabulate_mcp.ipynb
```

The notebook will guide you through:
1. Installing dependencies
2. Verifying existing infrastructure
3. Using existing Cognito user (parsed from config.yml)
4. Setting up IAM roles
5. Configuring AgentCore Runtime
6. Deploying the MCP server
7. Testing the deployment

**Note**: The deployment will automatically parse the username from your `config.yml` file. You can also specify a custom username as a parameter during deployment.

### Step 3: Test the Deployment
After deployment, run the test suite:
```bash
cd tests
pytest
```

Or test using the generated remote client:
```bash
python tests/test_client_remote.py
```

## Local Development and Testing

### Run MCP Server Locally
```bash
# Set environment variables
export STATE_MACHINE_ARN="arn:aws:states:us-east-1:081277383238:stateMachine:idp-bedrock-StepFunctions"
export BUCKET_NAME="idp-bedrock-data-081277383238"

# Install dependencies
pip install -r requirements.txt

# Run the server
python mcp_server.py
```

### Run Tests
```bash
# Run all tests
cd tests
pytest

# Run specific test file
pytest test_direct_http.py

# Run with verbose output
pytest -v
```

## Configuration

The MCP server uses the following configuration sources:

### Environment Variables
- `STATE_MACHINE_ARN`: ARN of the IDP Step Functions state machine
- `BUCKET_NAME`: Name of the S3 bucket for document storage
- `AWS_DEFAULT_REGION`: AWS region

### AWS Services Integration
- **Parameter Store**: `/idp-mcp/runtime/agent_arn` - Stores the deployed agent ARN
- **Secrets Manager**: `idp-mcp/cognito/credentials` - Stores authentication credentials
- **Cognito**: Uses existing user pool from IDP project

## Usage Examples

### Basic Document Extraction
```python
# Using MCP client
result = await session.call_tool(
    name="extract_document_attributes",
    arguments={
        "documents": ["originals/email_1.txt"],
        "attributes": [
            {"name": "customer_name", "description": "name of the customer"},
            {"name": "sentiment", "description": "sentiment score 0-1"}
        ]
    }
)
```

### Advanced Extraction with Custom Model
```python
result = await session.call_tool(
    name="extract_document_attributes",
    arguments={
        "documents": ["originals/financial_doc.pdf"],
        "attributes": [
            {"name": "total_amount", "description": "total financial amount"},
            {"name": "currency", "description": "currency code"}
        ],
        "parsing_mode": "Amazon Bedrock LLM",
        "model_params": {
            "model_id": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            "temperature": 0.1
        },
        "instructions": "Focus on numerical values and currency symbols"
    }
)
```

## Monitoring and Troubleshooting

### CloudWatch Logs
Monitor the MCP server through CloudWatch logs:
- Log Group: `/aws/bedrock-agentcore/runtimes/idp-mcp-*`

### Common Issues

1. **Authentication Errors**: Verify Cognito user pool configuration and bearer token
2. **Step Functions Failures**: Check Step Functions execution logs
3. **S3 Access Issues**: Verify bucket permissions and document paths
4. **Model Access**: Ensure Bedrock model access is enabled in your region

### Health Check
The MCP server provides a health check endpoint:
```
GET /health
```

## Security Considerations

- **Authentication**: Uses JWT tokens from Cognito user pool
- **Authorization**: IAM roles with least-privilege access
- **Network**: Deployed on AWS managed infrastructure
- **Data**: Documents processed in your AWS account, no data leaves your environment

## Cleanup

To remove the deployed MCP server:

1. Run the cleanup section in the deployment notebook, or
2. Manually delete:
   - AgentCore Runtime instance
   - ECR repository
   - IAM roles
   - Parameter Store parameters
   - Secrets Manager secrets

Note: The original IDP infrastructure (Step Functions, S3, Cognito) remains unchanged.

## Support

For issues or questions:
1. Check CloudWatch logs for error details
2. Verify all prerequisites are met
3. Ensure AWS credentials have required permissions
4. Run the test suite to identify issues

## License

This project follows the same license as the main IDP project.
