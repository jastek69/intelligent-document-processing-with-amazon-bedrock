"""
Utility functions for IDP with Amazon Bedrock MCP Server deployment
Integrates with existing Cognito user pool from the IDP project
"""

import boto3
import json
import time
from boto3.session import Session


def get_existing_cognito_config():
    """
    Retrieve existing Cognito configuration from the IDP project
    """
    boto_session = Session()
    region = boto_session.region_name
    ssm_client = boto3.client("ssm", region_name=region)

    try:
        # Get existing Cognito configuration from SSM parameters
        # These are created by the IDP project's Cognito construct
        stack_name = "idp-bedrock"  # From config.yml

        # Get Client ID
        client_id_param = ssm_client.get_parameter(Name=f"/{stack_name}/ecs/CLIENT_ID")
        client_id = client_id_param["Parameter"]["Value"]

        # Get User Pool ID
        user_pool_id_param = ssm_client.get_parameter(
            Name=f"/{stack_name[:16]}/ecs/USER_POOL_ID"  # Prefix is truncated to 16 chars
        )
        user_pool_id = user_pool_id_param["Parameter"]["Value"]

        # Get Cognito Domain
        domain_param = ssm_client.get_parameter(Name=f"/{stack_name}/ecs/COGNITO_DOMAIN")
        cognito_domain = domain_param["Parameter"]["Value"]

        # Construct discovery URL
        discovery_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration"

        print("✅ Found existing Cognito configuration:")
        print(f"   User Pool ID: {user_pool_id}")
        print(f"   Client ID: {client_id}")
        print(f"   Domain: {cognito_domain}")
        print(f"   Discovery URL: {discovery_url}")

        return {
            "user_pool_id": user_pool_id,
            "client_id": client_id,
            "cognito_domain": cognito_domain,
            "discovery_url": discovery_url,
            "region": region,
        }

    except Exception as e:
        print(f"❌ Error retrieving existing Cognito configuration: {e}")
        print("Make sure the IDP project is deployed with Cognito enabled")
        return None


def discover_step_functions_arn(region):
    """Discover Step Functions state machine ARN"""
    try:
        sf_client = boto3.client("stepfunctions", region_name=region)
        paginator = sf_client.get_paginator("list_state_machines")
        for page in paginator.paginate():
            for sm in page["stateMachines"]:
                if "idp-bedrock" in sm["name"].lower():
                    print(f"✅ Found Step Functions: {sm['stateMachineArn']}")
                    return sm["stateMachineArn"]
    except Exception as e:
        print(f"⚠️  Could not find Step Functions: {e}")
    return None


def discover_s3_bucket_name(region):
    """Discover S3 bucket name"""
    try:
        s3_client = boto3.client("s3", region_name=region)
        response = s3_client.list_buckets()
        for bucket in response["Buckets"]:
            if "idp-bedrock" in bucket["Name"].lower() and "data" in bucket["Name"].lower():
                print(f"✅ Found S3 bucket: {bucket['Name']}")
                return bucket["Name"]
    except Exception as e:
        print(f"⚠️  Could not find S3 bucket: {e}")
    return None


def try_expected_step_functions(region, account_id):
    """Try to find Step Functions using expected naming pattern"""
    expected_sm_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:idp-bedrock-StepFunctions"
    try:
        sf_client = boto3.client("stepfunctions", region_name=region)
        sf_client.describe_state_machine(stateMachineArn=expected_sm_arn)
        print(f"✅ Found Step Functions (expected name): {expected_sm_arn}")
        return expected_sm_arn
    except Exception as e:
        print(f"⚠️  Expected Step Functions not found: {e}")
    return None


def try_expected_s3_bucket(region, account_id):
    """Try to find S3 bucket using expected naming pattern"""
    expected_bucket = f"idp-bedrock-data-{account_id}"
    try:
        s3_client = boto3.client("s3", region_name=region)
        s3_client.head_bucket(Bucket=expected_bucket)
        print(f"✅ Found S3 bucket (expected name): {expected_bucket}")
        return expected_bucket
    except Exception as e:
        print(f"⚠️  Expected S3 bucket not found: {e}")
    return None


def get_existing_infrastructure_config():
    """Get existing IDP infrastructure configuration by discovering resources"""
    try:
        boto_session = Session()
        region = boto_session.region_name
        account_id = boto3.client("sts").get_caller_identity()["Account"]

        # Try to discover Step Functions state machine
        state_machine_arn = discover_step_functions_arn(region)
        if not state_machine_arn:
            state_machine_arn = try_expected_step_functions(region, account_id)

        # Try to discover S3 bucket
        bucket_name = discover_s3_bucket_name(region)
        if not bucket_name:
            bucket_name = try_expected_s3_bucket(region, account_id)

        # Validate that we found both resources
        if not state_machine_arn or not bucket_name:
            print("❌ Could not find required infrastructure resources")
            print("Please ensure the IDP project is deployed with:")
            print("  - Step Functions state machine (containing 'idp-bedrock')")
            print("  - S3 bucket (containing 'idp-bedrock-data')")
            return None

        return {"state_machine_arn": state_machine_arn, "bucket_name": bucket_name, "region": region}

    except Exception as e:
        print(f"❌ Error getting infrastructure config: {e}")
        return None


def list_cognito_users(cognito_client, user_pool_id):
    """List existing users in Cognito pool and return the first one"""
    try:
        response = cognito_client.list_users(UserPoolId=user_pool_id)
        users = response.get("Users", [])

        if not users:
            print("❌ No users found in Cognito pool")
            return None

        print("Available users:")
        for i, user in enumerate(users):
            user_attrs = {attr["Name"]: attr["Value"] for attr in user.get("Attributes", [])}
            email = user_attrs.get("email", "No email")
            print(f"  {i + 1}. {user['Username']} ({email})")

        # Use the first user (typically the main user from config.yml)
        username = users[0]["Username"]
        user_attrs = {attr["Name"]: attr["Value"] for attr in users[0].get("Attributes", [])}
        email = user_attrs.get("email", username)
        print(f"✅ Using existing user: {username} ({email})")
        return username

    except Exception as e:
        print(f"❌ Error listing users: {e}")
        return None


def get_user_password(username):
    """Get password for user, prompting if necessary"""
    print(f"⚠️  Password required for user: {username}")
    print("Please provide the password for this user, or set a new one in Cognito console")
    password = input(f"Enter password for {username}: ").strip()
    if not password:
        print("❌ Password is required")
        return None
    return password


def authenticate_cognito_user(cognito_client, cognito_config, username, password):
    """Authenticate user with Cognito and return bearer token"""
    try:
        auth_response = cognito_client.initiate_auth(
            ClientId=cognito_config["client_id"],
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )

        bearer_token = auth_response["AuthenticationResult"]["AccessToken"]
        print(f"✅ Successfully authenticated user: {username}")
        print("✅ Generated bearer token for MCP access")
        return bearer_token

    except cognito_client.exceptions.NotAuthorizedException:
        print(f"❌ Authentication failed for user: {username}")
        print("Please check the password or reset it in Cognito console")
        return None
    except cognito_client.exceptions.UserNotConfirmedException:
        return handle_unconfirmed_user(cognito_client, cognito_config, username, password)
    except Exception as auth_error:
        print(f"❌ Authentication error: {auth_error}")
        return None


def handle_unconfirmed_user(cognito_client, cognito_config, username, password):
    """Handle unconfirmed user by confirming and retrying authentication"""
    print(f"⚠️  User {username} is not confirmed. Attempting to confirm...")
    try:
        cognito_client.admin_confirm_sign_up(UserPoolId=cognito_config["user_pool_id"], Username=username)
        print(f"✅ User {username} confirmed")

        # Retry authentication
        auth_response = cognito_client.initiate_auth(
            ClientId=cognito_config["client_id"],
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": password},
        )
        bearer_token = auth_response["AuthenticationResult"]["AccessToken"]
        print(f"✅ Successfully authenticated user: {username}")
        return bearer_token
    except Exception as confirm_error:
        print(f"❌ Error confirming user: {confirm_error}")
        return None


def get_existing_user_credentials(cognito_config, username=None, password=None):
    """Use existing user in the Cognito user pool for MCP access"""
    try:
        cognito_client = boto3.client("cognito-idp", region_name=cognito_config["region"])
        user_pool_id = cognito_config["user_pool_id"]

        # Get username if not provided
        if not username:
            print("📋 Listing existing users in Cognito pool...")
            username = list_cognito_users(cognito_client, user_pool_id)
            if not username:
                return None

        # Get password if not provided
        if not password:
            password = get_user_password(username)
            if not password:
                return None

        # Authenticate user and get bearer token
        bearer_token = authenticate_cognito_user(cognito_client, cognito_config, username, password)
        if not bearer_token:
            return None

        return {"username": username, "password": password, "bearer_token": bearer_token}

    except Exception as e:
        print(f"❌ Error getting user credentials: {e}")
        return None


def create_mcp_user_in_existing_pool(cognito_config, username="egorkr@amazon.co.uk", password=None):
    """
    Wrapper function for backward compatibility - now uses existing users
    """
    return get_existing_user_credentials(cognito_config, username, password)


def create_agentcore_role(agent_name="idp-bedrock-mcp"):
    """
    Create IAM role for AgentCore Runtime with permissions for IDP resources
    """
    iam_client = boto3.client("iam")
    agentcore_role_name = f"agentcore-{agent_name}-role"
    boto_session = Session()
    region = boto_session.region_name
    account_id = boto3.client("sts").get_caller_identity()["Account"]

    role_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockPermissions",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": "*",
            },
            {
                "Sid": "StepFunctionsPermissions",
                "Effect": "Allow",
                "Action": ["states:StartExecution", "states:DescribeExecution", "states:GetExecutionHistory"],
                "Resource": [
                    f"arn:aws:states:{region}:{account_id}:stateMachine:idp-bedrock-*",
                    f"arn:aws:states:{region}:{account_id}:execution:idp-bedrock-*:*",
                ],
            },
            {
                "Sid": "S3Permissions",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:::idp-bedrock-data-{account_id}",
                    f"arn:aws:s3:::idp-bedrock-data-{account_id}/*",
                ],
            },
            {
                "Sid": "ECRImageAccess",
                "Effect": "Allow",
                "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:GetAuthorizationToken"],
                "Resource": [f"arn:aws:ecr:{region}:{account_id}:repository/*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogStreams", "logs:CreateLogGroup"],
                "Resource": [f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogGroups"],
                "Resource": [f"arn:aws:logs:{region}:{account_id}:log-group:*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                ],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                "Resource": ["*"],
            },
            {
                "Effect": "Allow",
                "Action": ["ecr:GetAuthorizationToken", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                "Resource": "*",
            },
            {
                "Sid": "ResourceDiscoveryPermissions",
                "Effect": "Allow",
                "Action": ["states:ListStateMachines", "s3:ListAllMyBuckets"],
                "Resource": "*",
            },
            {
                "Sid": "GetAgentAccessToken",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/*",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/{agent_name}-*",
                ],
            },
        ],
    }

    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": f"{account_id}"},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"},
                },
            }
        ],
    }

    assume_role_policy_document_json = json.dumps(assume_role_policy_document)
    role_policy_document = json.dumps(role_policy)

    # Create IAM Role
    try:
        agentcore_iam_role = iam_client.create_role(
            RoleName=agentcore_role_name, AssumeRolePolicyDocument=assume_role_policy_document_json
        )
        time.sleep(10)  # Wait for role creation
        print(f"✅ Created IAM role: {agentcore_role_name}")

    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"ℹ️  Role {agentcore_role_name} already exists, recreating...")

        # Delete existing policies
        policies = iam_client.list_role_policies(RoleName=agentcore_role_name, MaxItems=100)
        for policy_name in policies["PolicyNames"]:
            iam_client.delete_role_policy(RoleName=agentcore_role_name, PolicyName=policy_name)

        # Delete and recreate role
        iam_client.delete_role(RoleName=agentcore_role_name)
        agentcore_iam_role = iam_client.create_role(
            RoleName=agentcore_role_name, AssumeRolePolicyDocument=assume_role_policy_document_json
        )
        time.sleep(10)
        print(f"✅ Recreated IAM role: {agentcore_role_name}")

    # Attach policy
    try:
        iam_client.put_role_policy(
            PolicyDocument=role_policy_document, PolicyName="IDPBedrockAgentCorePolicy", RoleName=agentcore_role_name
        )
        print(f"✅ Attached policy to role: {agentcore_role_name}")
    except Exception as e:
        print(f"❌ Error attaching policy: {e}")

    return agentcore_iam_role


def store_mcp_configuration(agent_arn, cognito_config, mcp_user_config):
    """
    Store MCP configuration in AWS Systems Manager Parameter Store and Secrets Manager
    """
    boto_session = Session()
    region = boto_session.region_name

    ssm_client = boto3.client("ssm", region_name=region)
    secrets_client = boto3.client("secretsmanager", region_name=region)

    try:
        # Store agent ARN in Parameter Store
        ssm_client.put_parameter(
            Name="/idp-bedrock-mcp/runtime/agent_arn",
            Value=agent_arn,
            Type="String",
            Description="Agent ARN for IDP with Amazon Bedrock MCP server",
            Overwrite=True,
        )
        print("✅ Agent ARN stored in Parameter Store")

        # Store MCP credentials in Secrets Manager
        mcp_credentials = {
            "bearer_token": mcp_user_config["bearer_token"],
            "username": mcp_user_config["username"],
            "client_id": cognito_config["client_id"],
            "discovery_url": cognito_config["discovery_url"],
        }

        try:
            secrets_client.create_secret(
                Name="idp-bedrock-mcp/cognito/credentials",
                Description="Cognito credentials for IDP with Amazon Bedrock MCP server",
                SecretString=json.dumps(mcp_credentials),
            )
            print("✅ MCP credentials stored in Secrets Manager")
        except secrets_client.exceptions.ResourceExistsException:
            secrets_client.update_secret(
                SecretId="idp-bedrock-mcp/cognito/credentials", SecretString=json.dumps(mcp_credentials)
            )
            print("✅ MCP credentials updated in Secrets Manager")

        return True

    except Exception as e:
        print(f"❌ Error storing MCP configuration: {e}")
        return False
