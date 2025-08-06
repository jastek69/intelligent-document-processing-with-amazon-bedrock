# IDP Bedrock MCP Server

An MCP (Model Context Protocol) server that provides document attribute extraction capabilities using Amazon Bedrock and AWS document processing services.

## Features

- **Local File Upload**: Automatically uploads local files to S3 for processing
- **Multiple Input Types**: Supports local files, S3 keys, S3 URIs, and presigned URLs
- **Intelligent Document Processing**: Uses Amazon Bedrock LLM for attribute extraction
- **Batch Processing**: Process multiple documents in a single request
- **Multiple Parsing Modes**: Amazon Textract, Amazon Bedrock LLM, and Bedrock Data Automation

## Installation

## Configuration

The server requires AWS credentials and the following environment variables (optional - will auto-discover if not set):

- `STATE_MACHINE_ARN`: ARN of the Step Functions state machine
- `BUCKET_NAME`: S3 bucket name for document storage

### For Local Development:

First install the package in editable mode:
```bash
uv pip install -e .
```

Then add to your MCP settings, Cline example:

```json
{
  "mcpServers": {
    "idp-bedrock-stdio": {
      "command": "/Users/egorkr/Projects/tabulate/.venv/bin/idp-bedrock-mcp-server",
      "args": [],
      "env": {
        "FASTMCP_LOG_LEVEL": "ERROR"
      },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

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
