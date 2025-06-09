"""
Copyright © Amazon.com and Affiliates.
This code is being licensed under the terms of the Amazon Software License available at https://aws.amazon.com/asl/.
"""

from aws_cdk import Aws, Duration, RemovalPolicy
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_cdk import custom_resources as cr
from cdk_nag import NagPackSuppression, NagSuppressions
from constructs import Construct

"""
Creates a Cognito User Pool with associated resources for authentication.

Resources created:
1. Cognito User Pool
    - Auto-verifies email addresses
    - Configurable password policy (8+ chars, requires digits, lowercase, uppercase, symbols)
    - Email-only account recovery
    - Email sign-in alias enabled

2. MFA Configuration (when enabled)
    - Required TOTP (Time-based One-Time Password)
    - SMS authentication disabled

3. Cognito Domain
    - Format: {prefix}-{account_id}.auth.{region}.amazoncognito.com

4. User Pool Client
    - No client secret
    - Configurable access token validity
    - Supports password and SRP authentication
    - OAuth 2.0 with authorization code grant
    - Scopes: OpenID, Email, Profile, Cognito Admin
    - Default callback/logout URLs for localhost:8501

5. User Management
    - Automatic user creation from email list
    - Pre-verified email addresses
    - Email-based notifications

6. SSM Parameters
    - /{stack_name}/ecs/COGNITO_DOMAIN
    - /{stack_name}/ecs/CLIENT_ID
    - /{prefix}/ecs/USER_POOL_ID

Args:
    scope (Construct): The scope in which to define this construct
    construct_id (str): The scoped construct ID
    stack_name (str): Name of the stack, used for resource naming
    mfa_enabled (bool, optional): Enable MFA requirement. Defaults to True
    access_token_validity (int, optional): Token validity in minutes. Defaults to 60
    cognito_users (list[str], optional): List of user emails to create. Defaults to []

Outputs:
    - Cognito Client ID (CloudFormation output)
"""


class CognitoAuthenticationConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        stack_name: str,
        mfa_enabled: bool = True,
        access_token_validity: int = 60,
        cognito_users: list[str] = [],  # noqa: B006
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.stack_name = stack_name
        self.prefix = stack_name[:16]

        self.create_cognito_user_pool(mfa_enabled, access_token_validity, cognito_users)

        # Add cdk-nag suppression for COG3
        NagSuppressions.add_resource_suppressions(
            self.user_pool,
            [
                NagPackSuppression(
                    id="AwsSolutions-COG3",
                    reason="AdvancedSecurityMode is not configured, defaulting to OFF.",
                ),
            ],
            apply_to_children=True,
        )

    @property
    def user_pool_id(self):
        return self.user_pool.user_pool_id

    @property
    def client_id(self):
        return self.user_pool_client.user_pool_client_id

    @property
    def ssm_client_id(self):
        return self._ssm_client_id

    @property
    def ssm_user_pool_id(self):
        return self._ssm_user_pool_id

    @property
    def ssm_cognito_domain(self):
        return self._ssm_cognito_domain

    def create_cognito_user_pool(self, mfa_enabled: bool, access_token_validity: int, cognito_users: list):
        # Cognito User Pool
        user_pool_common_config = {
            "user_pool_name": f"{self.prefix}-user-pool-{Aws.ACCOUNT_ID}-{Aws.REGION}",
            "auto_verify": cognito.AutoVerifiedAttrs(email=True),
            "removal_policy": RemovalPolicy.DESTROY,
            "password_policy": cognito.PasswordPolicy(
                min_length=8,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=True,
            ),
            "account_recovery": cognito.AccountRecovery.EMAIL_ONLY,
            "sign_in_aliases": cognito.SignInAliases(email=True),
        }

        # Construct ID for the UserPool
        user_pool_construct_id = f"{self.prefix}-user-pool-resource"

        if mfa_enabled:
            user_pool_mfa_config = {
                "mfa": cognito.Mfa.REQUIRED,
                "mfa_second_factor": cognito.MfaSecondFactor(sms=False, otp=True),
            }
            self.user_pool = cognito.UserPool(
                self,
                user_pool_construct_id,
                **user_pool_common_config,
                **user_pool_mfa_config,
            )
        else:
            self.user_pool = cognito.UserPool(self, user_pool_construct_id, **user_pool_common_config)
            # If MFA is not enabled, COG2 will trigger. Suppress it here.
            NagSuppressions.add_resource_suppressions(
                self.user_pool,
                [
                    NagPackSuppression(
                        id="AwsSolutions-COG2",
                        reason="MFA is explicitly disabled for this deployment configuration.",
                    ),
                ],
                apply_to_children=True,
            )

        self.user_pool.add_domain(
            "CognitoDomain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix=f"{self.prefix}-{Aws.ACCOUNT_ID}"),
        )

        self.user_pool_client = self.user_pool.add_client(
            "customer-app-client",
            user_pool_client_name=f"{self.prefix}-client",
            generate_secret=False,
            access_token_validity=Duration.minutes(access_token_validity),
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO],
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                    cognito.OAuthScope.COGNITO_ADMIN,
                ],
                callback_urls=["http://localhost:8501"],
                logout_urls=["http://localhost:8501"],
            ),
        )

        # Add users to the pool
        for email in cognito_users:
            cognito.CfnUserPoolUser(
                self,
                f"CognitoUser-{email}",
                user_pool_id=self.user_pool.user_pool_id,
                username=email,
                desired_delivery_mediums=["EMAIL"],
                force_alias_creation=True,
                user_attributes=[
                    cognito.CfnUserPoolUser.AttributeTypeProperty(name="email", value=email),
                    cognito.CfnUserPoolUser.AttributeTypeProperty(name="email_verified", value="true"),
                ],
            )

        # ********* Store COGNITO_DOMAIN in SSM Parameter Store *********
        cognito_domain = f"{self.prefix}-{Aws.ACCOUNT_ID}.auth.{Aws.REGION}.amazoncognito.com"
        self._ssm_cognito_domain = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmCognitoDomain",
            parameter_name=f"/{self.stack_name}/ecs/COGNITO_DOMAIN",
            string_value=cognito_domain,
            description="Cognito domain for authentication",
        )

        self._ssm_client_id = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmClientId",
            parameter_name=f"/{self.stack_name}/ecs/CLIENT_ID",
            string_value=self.client_id,
        )

        self._ssm_user_pool_id = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmUserPoolId",
            parameter_name=f"/{self.prefix}/ecs/USER_POOL_ID",
            string_value=self.user_pool_id,
        )


class CognitoCallbackUpdater(Construct):
    """
    A construct that updates Cognito User Pool Client callback URLs.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        user_pool_id: str,
        client_id: str,
        cloudfront_domain: str,
        **kwargs,
    ) -> None:
        """
        Initialize the CognitoCallbackUpdater construct.

        Args:
            scope: The scope in which to define this construct.
            construct_id: The scoped construct ID.
            user_pool_id: The Cognito User Pool ID.
            client_id: The Cognito User Pool Client ID.
            cloudfront_domain: The CloudFront distribution domain name.
        """
        super().__init__(scope, construct_id, **kwargs)

        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.cloudfront_domain = cloudfront_domain

        # Create the custom resource role
        updater_role = iam.Role(
            self,
            "CognitoUpdaterRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        # Add permissions to update Cognito User Pool Client
        updater_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:UpdateUserPoolClient",
                    "cognito-idp:DescribeUserPoolClient",
                ],
                resources=[f"arn:aws:cognito-idp:{scope.region}:{scope.account}:userpool/{user_pool_id}"],
            )
        )

        # Add CloudWatch Logs permissions
        updater_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[f"arn:aws:logs:{scope.region}:{scope.account}:log-group:/aws/lambda/*"],
            )
        )

        # First, get the current configuration
        self.describe_client = cr.AwsCustomResource(
            self,
            "DescribeUserPoolClient",
            on_update=cr.AwsSdkCall(
                service="CognitoIdentityServiceProvider",
                action="describeUserPoolClient",
                parameters={
                    "UserPoolId": user_pool_id,
                    "ClientId": client_id,
                },
                physical_resource_id=cr.PhysicalResourceId.of(f"{user_pool_id}-{client_id}-describe"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[f"arn:aws:cognito-idp:{scope.region}:{scope.account}:userpool/{user_pool_id}"]
            ),
            role=updater_role,
        )

        # Update the client with new callback URLs
        self.update_client = cr.AwsCustomResource(
            self,
            "UpdateUserPoolClient",
            on_update=cr.AwsSdkCall(
                service="CognitoIdentityServiceProvider",
                action="updateUserPoolClient",
                parameters={
                    "UserPoolId": user_pool_id,
                    "ClientId": client_id,
                    "CallbackURLs": [
                        "http://localhost:8501",
                        f"https://{cloudfront_domain}/oauth2/idpresponse",
                        f"https://{cloudfront_domain}/",
                    ],
                    "LogoutURLs": [
                        "http://localhost:8501",
                        f"https://{cloudfront_domain}",
                    ],
                    "AllowedOAuthFlows": ["code"],
                    "AllowedOAuthScopes": [
                        "openid",
                        "email",
                        "profile",
                        "aws.cognito.signin.user.admin",
                    ],
                    "AllowedOAuthFlowsUserPoolClient": True,
                    "SupportedIdentityProviders": ["COGNITO"],
                },
                physical_resource_id=cr.PhysicalResourceId.of(f"{user_pool_id}-{client_id}-update"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[f"arn:aws:cognito-idp:{scope.region}:{scope.account}:userpool/{user_pool_id}"]
            ),
            role=updater_role,
        )

        # Ensure update happens after describe
        self.update_client.node.add_dependency(self.describe_client)

        self.add_nag_suppressions()

    def add_nag_suppressions(self) -> None:
        """Adds NagSuppressions to the construct."""
        # This might be necessary if cdk-nag flags the CR provider framework Lambdas.
        NagSuppressions.add_resource_suppressions(
            [self.describe_client, self.update_client],
            [
                NagPackSuppression(
                    id="AwsSolutions-L1",
                    reason="Runtime for AWS Custom Resource Lambda functions is managed by the CDK/Provider framework.",
                )
            ],
            apply_to_children=True,
        )
