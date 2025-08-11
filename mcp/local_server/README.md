# IDP Bedrock MCP Server (Stdio)

An MCP (Model Context Protocol) server that provides document attribute extraction capabilities using Amazon Bedrock and AWS document processing services. This is the **stdio (local) version** that runs locally and supports direct file upload.

## Features

- **Local File Upload**: Automatically uploads local files to S3 for processing
- **Multiple Input Types**: Supports local files, S3 keys, S3 URIs, and presigned URLs
- **Intelligent Document Processing**: Uses Amazon Bedrock LLM for attribute extraction
- **Batch Processing**: Process multiple documents in a single request
- **Multiple Parsing Modes**: Amazon Textract, Amazon Bedrock LLM, and Bedrock Data Automation
- **Easy Installation**: One-script deployment with automatic configuration generation

## Quick Setup

### Automated Deployment (Recommended)

Run the deployment script from the `mcp/local_server/` directory:

```bash
cd mcp/local_server/
./deploy_stdio_server.sh
```

This script will:
1. Navigate to the repo root and install the package with `uv pip install -e .`
2. Generate MCP configuration JSON file with correct paths
3. Display setup instructions with the configuration file path

### Manual Setup

If you prefer manual setup:

```bash
# From the repo root directory
uv pip install -e .
```

## Configuration

The server requires AWS credentials and will auto-discover the following (optional environment variables):

- `STATE_MACHINE_ARN`: ARN of the Step Functions state machine
- `BUCKET_NAME`: S3 bucket name for document storage

### MCP Client Configuration:

After running the deployment script, copy the configuration from `configs/mcp_stdio_config.json`:

```json
{
  "mcpServers": {
    "idp-bedrock-stdio": {
      "disabled": false,
      "timeout": 30000,
      "type": "stdio",
      "command": "/path/to/.venv/bin/idp-bedrock-mcp-server",
      "args": [],
      "autoApprove": [],
      "env": {},
      "debug": true
    }
  }
}
```

Add this configuration to your MCP client settings file.

Refer to your specific MCP client documentation for the correct configuration file location and format.

### For Published Package (Future):

Once published to PyPI, you can use:

```json
{
  "mcpServers": {
    "idp-bedrock-stdio": {
      "command": "uvx",
      "args": ["idp-bedrock-mcp-server@latest"],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Available Tools

### extract_document_attributes

Extract custom attributes from documents using Amazon Bedrock.

**Parameters:**
- `documents`: List of document paths (local files, S3 keys, S3 URIs, presigned URLs)
- `attributes`: List of attribute definitions to extract
- `parsing_mode`: Parsing mode ("Amazon Textract", "Amazon Bedrock LLM", "Bedrock Data Automation")
- `instructions`: Optional high-level instructions
- `few_shots`: Optional example input/output pairs
- `model_params`: Model configuration parameters

**Example:**
```python
{
  "documents": ["./invoice.pdf", "s3://bucket/document.txt"],
  "attributes": [
    {
      "name": "company_name",
      "description": "Name of the company",
      "type": "character"
    },
    {
      "name": "amount",
      "description": "Total amount",
      "type": "character"
    }
  ],
  "parsing_mode": "Amazon Bedrock LLM"
}
```

### get_extraction_status

Check the status of a document extraction operation.

### list_supported_models

Get the list of supported Amazon Bedrock models.

### get_bucket_info

Get information about the S3 bucket configuration.

## Supported Document Types

- **Text files**: .txt
- **PDF files**: .pdf
- **Images**: .jpg, .jpeg, .png
- **Office files**: .doc, .docx, .ppt, .pptx, .xls, .xlsx
- **Web files**: .html, .htm, .md, .csv

## Input Types

1. **Local files**: Automatically uploaded to S3 (e.g., `./document.pdf`)
2. **S3 keys**: Used directly if in configured bucket (e.g., `originals/file.txt`)
3. **S3 URIs**: Copied from external buckets (e.g., `s3://bucket/file.pdf`)
4. **Presigned URLs**: Downloaded and processed

## Requirements

- Python 3.10+
- AWS credentials configured
- Access to Amazon Bedrock and AWS document processing services

## License

MIT License
