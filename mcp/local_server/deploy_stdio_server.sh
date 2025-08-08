#!/bin/bash

# Deploy IDP Bedrock MCP Stdio Server
# This script installs the package and generates MCP configuration for local development

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo "${CYAN}$1${NC}"
}

print_success() {
    echo "${GREEN}✅ $1${NC}"
}

print_error() {
    echo "${RED}❌ $1${NC}"
}

print_warning() {
    echo "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo "${BLUE}ℹ️  $1${NC}"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Deploy IDP Bedrock MCP Stdio Server for local development"
    echo ""
    echo "Options:"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "This script will:"
    echo "  1. Navigate to the repo root and install the package with 'uv pip install -e .'"
    echo "  2. Generate MCP configuration JSON for Cline/Amazon Q"
    echo "  3. Display setup instructions"
}

# Function to find the repo root
find_repo_root() {
    local current_dir="$(pwd)"
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Go up from local_server -> mcp -> internal (repo root)
    local repo_root="$(cd "$script_dir/../../" && pwd)"

    # Verify this is the repo root by checking for pyproject.toml
    if [ ! -f "$repo_root/pyproject.toml" ]; then
        print_error "Could not find repo root. Expected pyproject.toml at: $repo_root"
        exit 1
    fi

    echo "$repo_root"
}

# Function to get the virtual environment python path
get_venv_python_path() {
    local repo_root="$1"

    # Check if we're in a virtual environment
    if [ -n "$VIRTUAL_ENV" ]; then
        echo "$VIRTUAL_ENV/bin/idp-bedrock-mcp-server"
        return 0
    fi

    # Check for .venv in repo root
    if [ -f "$repo_root/.venv/bin/idp-bedrock-mcp-server" ]; then
        echo "$repo_root/.venv/bin/idp-bedrock-mcp-server"
        return 0
    fi

    # Fallback to system python location (after installation)
    local python_path=$(which python3 2>/dev/null || which python 2>/dev/null)
    if [ -n "$python_path" ]; then
        local python_dir=$(dirname "$python_path")
        echo "$python_dir/idp-bedrock-mcp-server"
        return 0
    fi

    print_error "Could not determine Python executable path"
    exit 1
}

# Function to install the package
install_package() {
    local repo_root="$1"

    print_status "📦 Step 1: Installing IDP Bedrock MCP Server package..."
    print_info "Repository root: $repo_root"

    # Navigate to repo root
    cd "$repo_root"

    # Check if uv is available
    if ! command -v uv &> /dev/null; then
        print_error "uv is not installed. Please install uv first:"
        print_info "curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi

    # Install the package in editable mode
    print_info "Running: uv pip install -e ."
    if uv pip install -e .; then
        print_success "Package installed successfully!"
    else
        print_error "Failed to install package"
        exit 1
    fi
}

# Function to generate MCP configuration
generate_mcp_config() {
    local repo_root="$1"
    local script_dir="$2"

    print_status "📝 Step 2: Generating MCP configuration..."

    # Get the correct executable path
    local executable_path
    executable_path=$(get_venv_python_path "$repo_root")

    print_info "Executable path: $executable_path"

    # Create configs directory
    mkdir -p "$script_dir/configs"

    # Generate MCP configuration (Amazon Q CLI format)
    local mcp_config='{
  "mcpServers": {
    "idp-bedrock-stdio": {
      "disabled": false,
      "timeout": 30000,
      "type": "stdio",
      "command": "'$executable_path'",
      "args": [],
      "autoApprove": [],
      "env": {},
      "debug": true
    }
  }
}'

    # Save configuration file
    local config_file="$script_dir/configs/mcp_stdio_config.json"
    echo "$mcp_config" > "$config_file"

    print_success "Generated MCP configuration file:"
    print_info "📄 $config_file"
}

# Function to display setup instructions
display_instructions() {
    local script_dir="$1"
    local executable_path="$2"
    local config_file="$3"

    print_status "🎉 Deployment Complete!"
    echo "============================================================"
    print_success "IDP Bedrock MCP Stdio Server has been successfully deployed!"
    echo ""

    print_info "📋 Setup Instructions:"
    echo ""

    print_status "MCP Configuration File:"
    print_info "📄 $config_file"
    echo ""

    print_status "Usage:"
    echo "1. Copy the configuration from the file above"
    echo "2. Add it to your MCP client settings (Amazon Q CLI, Cline, etc.)"
    echo ""

    print_status "📋 Configuration Preview:"
    echo "========================================"
    cat "$config_file"
    echo "========================================"
    echo ""

    print_info "📄 Configuration file path: $config_file"
    echo ""

    print_status "🔧 Available Tools:"
    echo "- extract_document_attributes: Extract custom attributes from documents"
    echo "- get_extraction_status: Check status of extractions"
    echo "- list_supported_models: Get available Bedrock models"
    echo "- get_bucket_info: Get S3 bucket information"
    echo ""

    print_success "The MCP server is now ready for local development! 🚀"
}

# Main function
main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    print_status "🚀 IDP Bedrock MCP Stdio Server Deployment"
    echo "============================================================"
    print_info "This script will install the package and generate MCP configuration"
    echo ""

    # Get current script directory and repo root
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local repo_root
    repo_root=$(find_repo_root)

    # Step 1: Install package
    install_package "$repo_root"

    # Step 2: Generate MCP configuration
    generate_mcp_config "$repo_root" "$script_dir"
    local config_file="$script_dir/configs/mcp_stdio_config.json"

    # Step 3: Display instructions
    local executable_path
    executable_path=$(get_venv_python_path "$repo_root")
    display_instructions "$script_dir" "$executable_path" "$config_file"
}

# Run main function with all arguments
main "$@"
