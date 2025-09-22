#!/bin/bash

# Update MCP Bearer Token
# This script fetches the latest bearer token from AWS Secrets Manager
# and updates your MCP client settings JSON file automatically.
#
# USAGE:
#   ./update_mcp_config.sh [OPTIONS]
#
# DESCRIPTION:
#   Bearer tokens for the IDP Bedrock MCP server expire periodically and need
#   to be refreshed. This script automates the process by:
#   1. Fetching the latest bearer token from AWS Secrets Manager
#   2. Locating your MCP client configuration file
#   3. Updating the idp-bedrock server configuration with the new token
#   4. Creating a backup of your config before making changes
#   5. Preserving all other settings unchanged
#
# OPTIONS:
#   -c, --config-path PATH    Path to MCP client settings JSON file
#                            Default: $HOME/.config/mcp/settings.json
#   -d, --dry-run            Show what would be updated without making changes
#   -h, --help               Show help message and exit
#
# EXAMPLES:
#   # Update using default config path
#   ./update_mcp_config.sh
#
#   # Test what would be updated (dry run)
#   ./update_mcp_config.sh --dry-run
#
#   # Use custom config file path
#   ./update_mcp_config.sh --config-path /path/to/your/mcp_settings.json
#
#   # Show help
#   ./update_mcp_config.sh --help
#
# REQUIREMENTS:
#   - jq (JSON processor): brew install jq  OR  sudo apt-get install jq
#   - aws CLI with configured credentials: aws configure
#   - Access to AWS Secrets Manager secret: idp-bedrock-mcp/cognito/credentials
#
# NOTES:
#   - The script will create a timestamped backup of your config file
#   - You may need to restart your MCP client after token update
#   - The script looks for servers with 'idp-bedrock' or 'bedrock-idp' in the name
#   - Only the Authorization header is updated; all other settings are preserved

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default Cline config path
DEFAULT_CONFIG_PATH="$HOME/Library/Application Support/Code/User/globalStorage/asbx.amzn-cline/settings/cline_mcp_settings.json"

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
    echo "Update MCP Bearer Token from AWS Secrets Manager"
    echo ""
    echo "Options:"
    echo "  -c, --config-path PATH    Path to MCP client settings JSON file"
    echo "  -d, --dry-run            Show what would be updated without making changes"
    echo "  -h, --help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Use default MCP config path"
    echo "  $0 --config-path /custom/path.json   # Use custom config path"
    echo "  $0 --dry-run                         # Show what would be updated"
}

# Function to get bearer token from AWS Secrets Manager
get_bearer_token() {
    print_status "🔐 Fetching bearer token from AWS Secrets Manager..." >&2

    # Get the secret value
    local secret_json
    secret_json=$(aws secretsmanager get-secret-value \
        --secret-id "idp-bedrock-mcp/cognito/credentials" \
        --query SecretString \
        --output text 2>/dev/null)

    if [ $? -ne 0 ]; then
        print_error "Failed to retrieve secret from AWS Secrets Manager" >&2
        print_info "Make sure you have AWS credentials configured and access to the secret" >&2
        exit 1
    fi

    # Extract bearer token from JSON
    local bearer_token
    bearer_token=$(echo "$secret_json" | jq -r '.bearer_token' 2>/dev/null)

    if [ $? -ne 0 ] || [ "$bearer_token" = "null" ] || [ -z "$bearer_token" ]; then
        print_error "Failed to extract bearer token from secret" >&2
        exit 1
    fi

    print_success "Successfully retrieved bearer token from AWS Secrets Manager" >&2
    echo "$bearer_token"
}

# Function to update MCP config
update_mcp_config() {
    local config_path="$1"
    local new_token="$2"
    local dry_run="$3"

    # Check if config file exists
    if [ ! -f "$config_path" ]; then
        print_error "MCP settings file not found: $config_path"
        exit 1
    fi

    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        print_error "jq is required but not installed. Please install jq first."
        print_info "On macOS: brew install jq"
        print_info "On Ubuntu/Debian: sudo apt-get install jq"
        exit 1
    fi

    # Find the idp-bedrock server key
    local server_key
    server_key=$(jq -r '.mcpServers | to_entries[] | select(.key | test("idp.*bedrock|bedrock.*idp"; "i")) | .key' "$config_path" 2>/dev/null | head -n1)

    if [ -z "$server_key" ] || [ "$server_key" = "null" ]; then
        print_error "IDP Bedrock MCP server configuration not found in MCP settings"
        print_info "Looking for servers with 'idp-bedrock' or 'bedrock-idp' in the name"
        exit 1
    fi

    # Get current token for comparison
    local old_token
    old_token=$(jq -r ".mcpServers[\"$server_key\"].headers.Authorization // \"\"" "$config_path" 2>/dev/null | sed 's/Bearer //' | cut -c1-50)

    if [ "$dry_run" = "true" ]; then
        print_status "🔍 DRY RUN - Would update the following:"
        print_info "Config file: $config_path"
        print_info "Server: $server_key"
        print_info "Old token: ${old_token}..."
        print_info "New token: $(echo "$new_token" | cut -c1-50)..."
        print_info "(No changes made)"
        return 0
    fi

    # Create backup
    local backup_path="${config_path}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$config_path" "$backup_path"
    print_info "Created backup: $backup_path"

    # Update the bearer token
    local temp_file
    temp_file=$(mktemp)

    jq ".mcpServers[\"$server_key\"].headers.Authorization = \"Bearer $new_token\"" "$config_path" > "$temp_file"

    if [ $? -eq 0 ]; then
        mv "$temp_file" "$config_path"
        print_success "Successfully updated bearer token in MCP settings"
        print_info "Server: $server_key"
        print_info "Config: $config_path"
        print_info "Old token: ${old_token}..."
        print_info "New token: $(echo "$new_token" | cut -c1-50)..."
    else
        rm -f "$temp_file"
        print_error "Failed to update configuration file"
        exit 1
    fi
}

# Main function
main() {
    local config_path="$DEFAULT_CONFIG_PATH"
    local dry_run="false"

    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -c|--config-path)
                config_path="$2"
                shift 2
                ;;
            -d|--dry-run)
                dry_run="true"
                shift
                ;;
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

    print_status "🔄 Updating MCP Bearer Token..."
    echo "=================================================="

    print_info "Config file: $config_path"

    # Get new bearer token
    local new_token
    new_token=$(get_bearer_token)

    # Update MCP configuration
    print_status "📝 Updating MCP configuration..."
    update_mcp_config "$config_path" "$new_token" "$dry_run"

    if [ "$dry_run" = "false" ]; then
        echo ""
        print_success "Bearer token update completed successfully!"
        print_warning "You may need to restart your MCP client for changes to take effect."
    fi
}

# Run main function with all arguments
main "$@"
