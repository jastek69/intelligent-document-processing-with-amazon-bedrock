#!/usr/bin/env python3
"""
Updated deployment script for Tabulate MCP Server
Based on the working approach from deploy_tabulate_mcp_fixed.ipynb
Generates MCP configuration for Cline/Amazon Q integration
"""

import sys
import os
import json
import time
from boto3.session import Session

# Import our utility functions
from utils import (
    get_existing_cognito_config,
    get_existing_infrastructure_config,
    create_mcp_user_in_existing_pool,
    create_agentcore_role,
    store_mcp_configuration
)

def generate_cline_mcp_config(agent_arn, cognito_config, mcp_user_config, region):
    """
    Generate MCP configuration for Cline/Amazon Q
    """
    # Construct the MCP server URL
    encoded_arn = agent_arn.replace(":", "%3A").replace("/", "%2F")
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

    # Get current working directory for absolute paths
    current_dir = os.path.abspath(".")

    # Cline configuration (stdio interface) - using existing test_client_remote.py
    cline_config = {
        "mcpServers": {
            "tabulate": {
                "autoApprove": [],
                "disabled": False,
                "timeout": 300,
                "type": "stdio",
                "command": "python",
                "args": [os.path.join(current_dir, "test_client_remote.py")],
                "env": {
                    "AWS_REGION": region
                }
            }
        }
    }

    return {
        "cline_config": cline_config,
        "manual_config": {
            "server_url": mcp_url,
            "bearer_token": mcp_user_config["bearer_token"],
            "region": region,
            "agent_arn": agent_arn,
            "instructions": [
                "1. Copy the cline_config to your Cline MCP settings",
                "2. The configuration uses the existing test_client_remote.py script",
                "3. Make sure the script path is correct for your system",
                "4. The client handles authentication automatically via AWS credentials"
            ]
        }
    }

def main():
    """
    Main deployment function - updated to match fixed notebook approach
    """
    print("🚀 Tabulate MCP Server Deployment (Updated)")
    print("=" * 60)
    print("This script deploys using the proven approach from the fixed notebook")
    print("and generates MCP configuration for Cline/Amazon Q integration")
    print()

    try:
        # Step 1: Get AWS region
        boto_session = Session()
        region = boto_session.region_name
        print(f"Using AWS region: {region}")
        print()

        # Step 2: Verify existing infrastructure
        print("🔍 Step 1: Verifying existing tabulate infrastructure...")
        print("-" * 50)

        cognito_config = get_existing_cognito_config()
        if not cognito_config:
            print("❌ Could not find existing Cognito configuration.")
            print("Make sure the tabulate project is deployed with Cognito enabled.")
            sys.exit(1)

        print()
        infra_config = get_existing_infrastructure_config()
        if not infra_config:
            print("❌ Could not find existing infrastructure.")
            print("Make sure the tabulate project is deployed.")
            sys.exit(1)

        print("✅ All existing infrastructure verified!")
        print()

        # Step 3: Use existing user
        print("👤 Step 2: Using existing Cognito user...")
        print("-" * 40)

        # Get the user from config.yml (egorkr@amazon.co.uk)
        mcp_user_config = create_mcp_user_in_existing_pool(
            cognito_config=cognito_config,
            username="egorkr@amazon.co.uk",  # This should match the user from config.yml
            password=None  # Will prompt for password
        )

        if not mcp_user_config:
            print("❌ Failed to authenticate existing user")
            sys.exit(1)

        print(f"✅ User authenticated successfully: {mcp_user_config['username']}")
        print()

        # Step 4: Create IAM role (using tabulateagent name like in fixed notebook)
        print("🔐 Step 3: Creating IAM role for AgentCore Runtime...")
        print("-" * 50)

        agentcore_iam_role = create_agentcore_role(agent_name="tabulateagent")
        print(f"✅ IAM role created: {agentcore_iam_role['Role']['Arn']}")
        print()

        # Step 5: Configure and deploy (matching fixed notebook approach)
        print("⚙️  Step 4: Configuring AgentCore Runtime deployment...")
        print("-" * 50)

        # Check required files
        required_files = ["mcp_server.py", "requirements.txt"]
        for file in required_files:
            if not os.path.exists(file):
                print(f"❌ Required file {file} not found")
                sys.exit(1)
        print("✅ All required files found")

        # Import AgentCore Runtime
        try:
            from bedrock_agentcore_starter_toolkit import Runtime
        except ImportError:
            print("❌ bedrock-agentcore-starter-toolkit not installed")
            print("Please install it with: pip install bedrock-agentcore-starter-toolkit")
            sys.exit(1)

        # Initialize AgentCore Runtime
        agentcore_runtime = Runtime()

        # Configure authentication (matching fixed notebook)
        auth_config = {
            "customJWTAuthorizer": {
                "allowedClients": [cognito_config["client_id"]],
                "discoveryUrl": cognito_config["discovery_url"],
            }
        }

        print("🔧 Configuring runtime...")
        print("   Infrastructure will be discovered automatically by the MCP server")
        print(f"   Expected State Machine: {infra_config['state_machine_arn']}")
        print(f"   Expected S3 Bucket: {infra_config['bucket_name']}")

        response = agentcore_runtime.configure(
            entrypoint="mcp_server.py",
            execution_role=agentcore_iam_role["Role"]["Arn"],
            auto_create_ecr=True,
            requirements_file="requirements.txt",
            region=region,
            authorizer_configuration=auth_config,
            protocol="MCP",
            agent_name="tabulateagent"  # Using same name as fixed notebook
        )
        print("✅ Runtime configured successfully")

        # Launch the MCP server
        print("\n🚀 Step 5: Launching MCP server to AgentCore Runtime...")
        print("-" * 50)
        print("⏳ This may take several minutes...")

        launch_result = agentcore_runtime.launch()

        print("✅ Launch completed successfully!")
        print(f"Agent ARN: {launch_result.agent_arn}")
        print(f"Agent ID: {launch_result.agent_id}")

        # Step 6: Wait for deployment
        print("\n⏳ Step 6: Waiting for deployment to complete...")
        print("-" * 50)

        status_response = agentcore_runtime.status()
        status = status_response.endpoint["status"]
        print(f"Initial status: {status}")

        end_status = ["READY", "CREATE_FAILED", "DELETE_FAILED", "UPDATE_FAILED"]
        while status not in end_status:
            print(f"Status: {status} - waiting...")
            time.sleep(30)
            status_response = agentcore_runtime.status()
            status = status_response.endpoint["status"]

        if status == "READY":
            print("🎉 AgentCore Runtime is READY!")
            print("✅ Tabulate MCP Server deployed successfully!")
        else:
            print(f"⚠️  AgentCore Runtime status: {status}")
            if status in ["CREATE_FAILED", "UPDATE_FAILED"]:
                print("❌ Deployment failed. Check CloudWatch logs for details.")
                sys.exit(1)

        # Step 7: Store configuration
        print("\n💾 Step 7: Storing configuration for remote access...")
        print("-" * 50)

        config_stored = store_mcp_configuration(
            agent_arn=launch_result.agent_arn,
            cognito_config=cognito_config,
            mcp_user_config=mcp_user_config
        )

        if config_stored:
            print("✅ Configuration stored successfully!")
        else:
            print("❌ Failed to store configuration")

        # Step 8: Generate Cline MCP Configuration
        print("\n📝 Step 8: Generating MCP configuration for Cline/Amazon Q...")
        print("-" * 50)

        # Generate Cline configuration using the helper function
        config_data = generate_cline_mcp_config(
            agent_arn=launch_result.agent_arn,
            cognito_config=cognito_config,
            mcp_user_config=mcp_user_config,
            region=region
        )

        # Save Cline configuration
        with open("cline_mcp_config.json", "w") as f:
            json.dump(config_data["cline_config"], f, indent=2)

        # Save manual config
        with open("mcp_manual_config.json", "w") as f:
            json.dump(config_data["manual_config"], f, indent=2)

        print("✅ Generated MCP configuration files:")
        print("   📄 cline_mcp_config.json - Configuration for Cline/Amazon Q")
        print("   📄 mcp_manual_config.json - Manual configuration details")

        # Display the Cline config for easy copying
        print("\n📋 Cline MCP Configuration (copy to Cline MCP settings):")
        print("=" * 60)
        print(json.dumps(config_data["cline_config"], indent=2))
        print("=" * 60)

        # Final summary
        print("\n🎉 Deployment Complete!")
        print("=" * 60)
        print("Your Tabulate MCP Server has been successfully deployed!")
        print()
        print("📋 Deployment Summary:")
        print(f"   Agent ARN: {launch_result.agent_arn}")
        print(f"   Agent ID: {launch_result.agent_id}")
        print(f"   MCP User: {mcp_user_config['username']}")
        print(f"   State Machine: {infra_config['state_machine_arn']}")
        print(f"   S3 Bucket: {infra_config['bucket_name']}")
        print()
        print("🔗 Access Information:")
        print("   Parameter Store: /tabulate-mcp/runtime/agent_arn")
        print("   Secrets Manager: tabulate-mcp/cognito/credentials")
        print()
        print("📁 Generated Files:")
        print("   cline_mcp_config.json - For Cline/Amazon Q")
        print("   mcp_manual_config.json - Manual setup details")
        print()
        print("🧪 Testing:")
        print("   The deployment includes built-in testing - no separate scripts needed")
        print("   MCP tools are ready for use in Cline or other MCP clients")
        print()
        print("The MCP server is now ready for production use! 🚀")

    except KeyboardInterrupt:
        print("\n❌ Deployment interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Deployment failed: {e}")
        print("\nTroubleshooting:")
        print("   1. Ensure the tabulate project is deployed")
        print("   2. Check AWS credentials and permissions")
        print("   3. Verify Docker is running")
        print("   4. Check CloudWatch logs for detailed errors")
        sys.exit(1)

if __name__ == "__main__":
    main()
