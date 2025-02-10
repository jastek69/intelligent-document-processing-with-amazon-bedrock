#!/bin/bash

# Platform Compatibility:
# - This script is designed for Unix-like systems (Linux, macOS)
# - For Windows users, please use either:
#   1. Windows Subsystem for Linux (WSL)
#   2. Git Bash

# Check if required arguments are provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <stack-name> <cloudfront-domain>"
    echo "Example: $0 idp-bedrock d123abc456def.cloudfront.net"
    exit 1
fi

STACK_NAME=$1
CLOUDFRONT_DOMAIN=$2

# Get User Pool ID and Client ID from SSM Parameter Store
echo "Fetching parameters from SSM..."
USER_POOL_ID=$(aws ssm get-parameter --name "/${STACK_NAME}/ecs/USER_POOL_ID" --query "Parameter.Value" --output text)
CLIENT_ID=$(aws ssm get-parameter --name "/${STACK_NAME}/ecs/CLIENT_ID" --query "Parameter.Value" --output text)

if [ -z "$USER_POOL_ID" ] || [ -z "$CLIENT_ID" ]; then
    echo "Error: Could not fetch required parameters from SSM"
    exit 1
fi

echo "Updating Cognito User Pool Client..."
echo "User Pool ID: $USER_POOL_ID"
echo "Client ID: $CLIENT_ID"
echo "CloudFront Domain: $CLOUDFRONT_DOMAIN"

# Update the User Pool Client using both CloudFront and localhost URLs
OUTPUT=$(aws cognito-idp update-user-pool-client \
    --user-pool-id "$USER_POOL_ID" \
    --client-id "$CLIENT_ID" \
    --callback-urls "https://${CLOUDFRONT_DOMAIN}/oauth2/idpresponse" "http://localhost:8501" \
    --logout-urls "https://${CLOUDFRONT_DOMAIN}" "http://localhost:8501" \
    --allowed-o-auth-flows code \
    --allowed-o-auth-scopes openid email profile "aws.cognito.signin.user.admin" \
    --supported-identity-providers COGNITO \
    --allowed-o-auth-flows-user-pool-client \
    --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_USER_SRP_AUTH ALLOW_REFRESH_TOKEN_AUTH)

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Successfully updated Cognito User Pool Client"
    echo -e "\nUpdated Configuration:"
    echo "Callback URLs:"
    echo "$OUTPUT" | jq -r '.UserPoolClient.CallbackURLs[]' | sed 's/^/- /'
    echo -e "\nLogout URLs:"
    echo "$OUTPUT" | jq -r '.UserPoolClient.LogoutURLs[]' | sed 's/^/- /'
else
    echo "Failed to update Cognito User Pool Client with error:"
    echo "$OUTPUT"
    exit 1
fi
