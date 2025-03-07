"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    IDP Bedrock API constructs
"""

import json

import aws_cdk.aws_apigatewayv2 as _apigw
import aws_cdk.aws_apigatewayv2_integrations as _integrations
from aws_cdk import Aws, Duration, RemovalPolicy
from aws_cdk import CfnOutput as output
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as ddb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as _s3
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk.aws_apigatewayv2_authorizers import HttpUserPoolAuthorizer
from cdk_nag import NagPackSuppression, NagSuppressions
from constructs import Construct

# https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-mapping-template-reference.html#context-variable-reference
HTTP_API_SERVICE_ACCESS_LOGS_FORMATTER = {
    "requestId": "$context.requestId",
    "userAgent": "$context.identity.userAgent",
    "sourceIp": "$context.identity.sourceIp",
    "requestTime": "$context.requestTime",
    "httpMethod": "$context.httpMethod",
    "path": "$context.path",
    "status": "$context.status",
    "responseLength": "$context.responseLength",
}

QUERY_BEDROCK_TIMEOUT = 900
TEXTRACT_TIMEOUT = 900
PRESIGNED_URL_TIMEOUT = 900

POWERPOINT_EXTENSIONS = (".ppt", ".pptx")
WORD_EXTENSIONS = (".doc", ".docx")
EXCEL_EXTENSIONS = (".xls", ".xlsx")
HTML_EXTENSIONS = (".html", ".htm")
MARKDOWN_EXTENSIONS = (".md", ".markdown")


class IDPBedrockAPIConstructs(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        stack_name,
        s3_data_bucket: _s3.Bucket,
        layers: Construct,
        bedrock_region: str,
        textract_region: str,
        architecture: _lambda.Architecture,
        python_runtime: _lambda.Runtime,
        table_flatten_headers: bool = True,
        table_remove_column_headers: bool = True,
        table_duplicate_text_in_merged_cells: bool = True,
        hide_footer_layout: bool = True,
        hide_header_layout: bool = True,
        hide_page_num_layout: bool = True,
        use_table: bool = True,
        mfa_enabled: bool = True,
        access_token_validity: int = 60,
        cognito_users: list[str] = [],  # noqa: B006
        s3_kms_key: kms.Key = None,
        **kwargs,
    ) -> None:
        """
        Initialize the IDP Bedrock API constructs

        Parameters
        ----------
        scope : Construct
            The scope of the construct
        construct_id : str
            The ID of the construct
        stack_name : str
            The name of the stack
        s3_data_bucket : _s3.Bucket
            The S3 bucket for storing data
        layers : Construct
            The layers for the construct
        bedrock_region : str
            The region for the Bedrock API
        textract_region : str
            The region for the Textract API
        architecture : _lambda.Architecture
            The architecture for the Lambda functions
        python_runtime : _lambda.Runtime
            The runtime for the Lambda functions
        table_flatten_headers : bool
            Whether to flatten headers in tables
        table_remove_column_headers : bool
            Whether to remove column headers in tables
        table_duplicate_text_in_merged_cells : bool
            Whether to duplicate text in merged cells in tables
        hide_footer_layout : bool
            Whether to hide footer layout
        hide_header_layout : bool
            Whether to hide header layout
        hide_page_num_layout : bool
            Whether to hide page number layout
        use_table : bool
            Whether to use tables
        mfa_enabled : bool
            Whether to enable MFA
        access_token_validity : int
            The validity of the access token
        s3_kms_key : kms.Key
            The KMS key for the S3 bucket
        """

        super().__init__(scope, construct_id, **kwargs)

        self.s3_data_bucket = s3_data_bucket
        self.bedrock_region = bedrock_region
        self.textract_region = textract_region
        self.table_flatten_headers = table_flatten_headers
        self.table_remove_column_headers = table_remove_column_headers
        self.table_duplicate_text_in_merged_cells = table_duplicate_text_in_merged_cells
        self.hide_footer_layout = hide_footer_layout
        self.hide_header_layout = hide_header_layout
        self.hide_page_num_layout = hide_page_num_layout
        self.use_table = use_table
        self.stack_name = stack_name
        self.layers = layers
        self._architecture = architecture
        self._python_runtime = python_runtime
        self.s3_kms_key = s3_kms_key
        self.documents_table_name = f"{stack_name}-documents"
        self.prefix = stack_name[:16]
        self.nag_suppressed_resources = []
        self.create_cognito_user_pool(mfa_enabled, access_token_validity, cognito_users)

        # Dependencies of the IDP Bedrock are included in idp_bedrock_deps layer (Lambda Powertools excluded)
        self.idp_bedrock_code_layers = [
            self.layers.idp_bedrock,
            self.layers.idp_bedrock_deps,
            self.layers.aws_lambda_powertools,
        ]
        self.textract_only_code_layers = [
            self.layers.textractor,
            self.layers.epd,
        ]

        ## **************** Create resources ****************
        self.create_dynamodb()
        self.create_roles()
        self.create_lambda_functions()
        self.create_stepfunction_role()
        self.create_stepfunctions()
        self.state_machine_arn = self.idp_bedrock_state_machine.state_machine_arn
        self.state_machine_arn_output = output(self, id="StepFunctionsARN", value=self.state_machine_arn)

        # authorizer = HttpIamAuthorizer()
        authorizer = HttpUserPoolAuthorizer(
            "BooksAuthorizer", self.user_pool, user_pool_clients=[self.user_pool_client]
        )

        # Create the HTTP API with CORS
        http_api = _apigw.HttpApi(
            self,
            f"{stack_name}-http-api",
            default_authorizer=authorizer,
            cors_preflight=_apigw.CorsPreflightOptions(
                allow_methods=[_apigw.CorsHttpMethod.POST],
                allow_origins=["*"],
                max_age=Duration.days(10),
            ),
        )
        http_api.add_routes(
            path="/url",
            methods=[_apigw.HttpMethod.POST],
            integration=_integrations.HttpLambdaIntegration(
                "LambdaProxyIntegration", handler=self.presigned_url_lambda
            ),
        )
        http_api.add_routes(
            path="/textract",
            methods=[_apigw.HttpMethod.POST],
            integration=_integrations.HttpLambdaIntegration("LambdaProxyIntegration", handler=self.textract_lambda),
        )
        http_api.add_routes(
            path="/attributes",
            methods=[_apigw.HttpMethod.POST],
            integration=_integrations.HttpLambdaIntegration("LambdaProxyIntegration", handler=self.attributes_lambda),
        )

        self.api_uri = http_api.api_endpoint
        self.ssm_api_uri = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmApiUri",
            parameter_name=f"/{self.stack_name}/ecs/API_URI",
            string_value=self.api_uri,
        )

        self.ssm_state_machine_arn = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmFilingsARN",
            parameter_name=f"/{self.stack_name}/ecs/STATE_MACHINE_ARN",
            string_value=self.state_machine_arn,
        )

        self.create_service_access_log_group(api_id=http_api.api_id)
        http_api.default_stage.node.default_child.access_log_settings = _apigw.CfnStage.AccessLogSettingsProperty(
            destination_arn=self.log_group.log_group_arn,
            format=json.dumps(HTTP_API_SERVICE_ACCESS_LOGS_FORMATTER),
        )

        self.add_nag_suppressions()

    def create_service_access_log_group(self, api_id: str) -> None:
        self.log_group = logs.LogGroup(
            self,
            f"{self.stack_name}-http-api-log-group",
            log_group_name=f"/aws/vendedlogs/apigateway/{self.stack_name}/{api_id}",  # Use vendedlogs prefix
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.TWO_WEEKS,
        )

    def create_cognito_user_pool(self, mfa_enabled: bool, access_token_validity: int, cognito_users: list):
        # Cognito User Pool
        user_pool_common_config = {
            "id": f"{self.prefix}-user-pool",
            "user_pool_name": f"{self.prefix}-user-pool",
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
            "advanced_security_mode": cognito.AdvancedSecurityMode.ENFORCED,
            "sign_in_aliases": cognito.SignInAliases(email=True),
        }

        if mfa_enabled:
            user_pool_mfa_config = {
                "mfa": cognito.Mfa.REQUIRED,
                "mfa_second_factor": cognito.MfaSecondFactor(sms=False, otp=True),
            }
            self.user_pool = cognito.UserPool(self, **user_pool_common_config, **user_pool_mfa_config)
        else:
            self.user_pool = cognito.UserPool(self, **user_pool_common_config)

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
        self.ssm_cognito_domain = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmCognitoDomain",
            parameter_name=f"/{self.stack_name}/ecs/COGNITO_DOMAIN",
            string_value=cognito_domain,
            description="Cognito domain for authentication",
        )

        self.client_id = self.user_pool_client.user_pool_client_id
        self.user_pool_id = self.user_pool.user_pool_id

        self.ssm_client_id = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmClientId",
            parameter_name=f"/{self.stack_name}/ecs/CLIENT_ID",
            string_value=self.client_id,
        )
        self.ssm_user_pool_id = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmUserPoolId",
            parameter_name=f"/{self.prefix}/ecs/USER_POOL_ID",
            string_value=self.user_pool_id,
        )

    def create_dynamodb(self):
        self.few_shots_table = ddb.Table(
            self,
            f"{self.stack_name}-few-shots",
            table_name=f"{self.stack_name}-few-shots",
            partition_key=ddb.Attribute(name="ExampleId", type=ddb.AttributeType.STRING),
            table_class=ddb.TableClass.STANDARD,
            billing_mode=ddb.BillingMode("PAY_PER_REQUEST"),
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True,
        )

    ## **************** Lambda Functions ****************
    def create_lambda_functions(self):
        ## ********* Get features *********
        self.attributes_lambda = _lambda.Function(
            self,
            f"{self.stack_name}-attributes-lambda",
            runtime=self._python_runtime,
            architecture=self._architecture,
            code=_lambda.Code.from_asset("./assets/lambda/backend/extract_attributes"),
            handler="extract_attributes.lambda_handler",
            function_name=f"{self.stack_name}-extract-attributes",
            memory_size=3008,
            timeout=Duration.seconds(QUERY_BEDROCK_TIMEOUT),
            environment={
                "BUCKET_NAME": self.s3_data_bucket.bucket_name,
                "BEDROCK_REGION": self.bedrock_region,
            },
            role=self.lambda_attributes_role,
            layers=self.idp_bedrock_code_layers,
        )
        self.attributes_lambda.add_alias(
            "Warm",
            provisioned_concurrent_executions=0,
            description="Alias used for Lambda provisioned concurrency",
        )

        ## ********* Run BDA *********
        self.bda_lambda = _lambda.Function(
            self,
            f"{self.stack_name}-bda-lambda",
            runtime=self._python_runtime,
            architecture=self._architecture,
            code=_lambda.Code.from_asset("./assets/lambda/backend/run_bedrock_automation"),
            handler="run_bedrock_automation.lambda_handler",
            function_name=f"{self.stack_name}-run-bda",
            memory_size=3008,
            timeout=Duration.seconds(QUERY_BEDROCK_TIMEOUT),
            environment={
                "BUCKET_NAME": self.s3_data_bucket.bucket_name,
                "BEDROCK_REGION": self.bedrock_region,
            },
            role=self.lambda_attributes_role,
            layers=self.idp_bedrock_code_layers,
        )
        self.bda_lambda.add_alias(
            "Warm",
            provisioned_concurrent_executions=0,
            description="Alias used for Lambda provisioned concurrency",
        )

        ## ********* Read Office files *********
        self.read_office_lambda = _lambda.DockerImageFunction(
            self,
            f"{self.stack_name}-read_office-docker-lambda",
            # runtime=self._python_runtime,
            # architecture=self._architecture,
            code=_lambda.DockerImageCode.from_image_asset(directory="./assets/lambda/backend/read_office_docker"),
            # handler="read_office.lambda_handler",
            function_name=f"{self.stack_name}-read_office_lambda",
            memory_size=3008,
            timeout=Duration.seconds(QUERY_BEDROCK_TIMEOUT),
            environment={
                "BUCKET_NAME": self.s3_data_bucket.bucket_name,
                "BEDROCK_REGION": self.bedrock_region,
                "POWERPOINT_EXTENSIONS": json.dumps(POWERPOINT_EXTENSIONS),
                "WORD_EXTENSIONS": json.dumps(WORD_EXTENSIONS),
                "EXCEL_EXTENSIONS": json.dumps(EXCEL_EXTENSIONS),
                "HTML_EXTENSIONS": json.dumps(HTML_EXTENSIONS),
                "MARKDOWN_EXTENSIONS": json.dumps(MARKDOWN_EXTENSIONS),
            },
            role=self.lambda_textract_role,
        )
        ## ********* Multimodal extract lambda *********
        self.llm_attributes_lambda = _lambda.DockerImageFunction(
            self,
            f"{self.stack_name}-attributes-llm-lambda",
            code=_lambda.DockerImageCode.from_image_asset("./assets/lambda/backend/extract_attributes_llm"),
            function_name=f"{self.stack_name}-extract-attributes-multimodal",
            memory_size=3008,
            timeout=Duration.seconds(QUERY_BEDROCK_TIMEOUT),
            environment={
                "BUCKET_NAME": self.s3_data_bucket.bucket_name,
                "BEDROCK_REGION": self.bedrock_region,
                "FEW_SHOTS_TABLE_NAME": self.few_shots_table.table_name,
            },
            role=self.lambda_attributes_role,  # TODO consider making a separate role?
        )
        self.llm_attributes_lambda.add_alias(
            "Warm",
            provisioned_concurrent_executions=0,
            description="Alias used for Lambda provisioned concurrency",
        )
        ## ********* Retrieve available examples from s3 lambda *********
        self.get_examples_list_lambda = _lambda.Function(
            self,
            f"{self.stack_name}-get-examples-list-lambda",
            runtime=self._python_runtime,
            architecture=self._architecture,
            code=_lambda.Code.from_asset("./assets/lambda/backend/dynamo_retrieve"),
            handler="retrieve_list.lambda_handler",
            function_name=f"{self.stack_name}-get-examples-list",
            memory_size=3008,
            timeout=Duration.seconds(QUERY_BEDROCK_TIMEOUT),
            environment={
                "FEW_SHOTS_TABLE_NAME": self.few_shots_table.table_name,
            },
            role=self.lambda_retrieve_examples_role,
        )
        self.get_examples_list_lambda.add_alias(
            "Warm",
            provisioned_concurrent_executions=0,
            description="Alias used for Lambda provisioned concurrency",
        )
        ## ********* Put example lambda *********
        self.put_example_lambda = _lambda.Function(
            self,
            f"{self.stack_name}-put-example-lambda",
            runtime=self._python_runtime,
            architecture=self._architecture,
            code=_lambda.Code.from_asset("./assets/lambda/backend/upload_few_shot"),
            handler="upload_few_shot.lambda_handler",
            function_name=f"{self.stack_name}-put-example",
            memory_size=3008,
            timeout=Duration.seconds(QUERY_BEDROCK_TIMEOUT),
            environment={
                "FEW_SHOTS_TABLE_NAME": self.few_shots_table.table_name,
            },
            role=self.lambda_retrieve_examples_role,
        )
        self.put_example_lambda.add_alias(
            "Warm",
            provisioned_concurrent_executions=0,
            description="Alias used for Lambda provisioned concurrency",
        )

        ## ********* Create presigned URL *********
        self.presigned_url_lambda = _lambda.Function(
            self,
            f"{self.stack_name}-presigned-url-lambda",
            runtime=self._python_runtime,
            architecture=self._architecture,
            code=_lambda.Code.from_asset("./assets/lambda/backend/get_presigned_url"),
            handler="get_presigned_url.lambda_handler",
            function_name=f"{self.stack_name}-get-presigned-url",
            memory_size=3008,
            timeout=Duration.seconds(PRESIGNED_URL_TIMEOUT),
            environment={
                "BUCKET_NAME": self.s3_data_bucket.bucket_name,
            },
            role=self.lambda_presigned_url_role,
        )
        self.presigned_url_lambda.add_alias(
            "Warm",
            provisioned_concurrent_executions=0,
            description="Alias used for Lambda provisioned concurrency",
        )

        ## ********* Process with Textract *********
        self.textract_lambda = _lambda.Function(
            self,
            f"{self.stack_name}-textract-lambda",
            runtime=self._python_runtime,
            code=_lambda.Code.from_asset("./assets/lambda/backend/run_textract"),
            handler="run_textract.lambda_handler",
            function_name=f"{self.stack_name}-run-textract",
            memory_size=3008,
            timeout=Duration.seconds(TEXTRACT_TIMEOUT),
            environment={
                "BUCKET_NAME": self.s3_data_bucket.bucket_name,
                "TEXTRACT_REGION": self.textract_region,
                "TABLE_FLATTEN_HEADERS": str(self.table_flatten_headers),
                "TABLE_REMOVE_COLUMN_HEADERS": str(self.table_remove_column_headers),
                "TABLE_DUPLICATE_TEXT_IN_MERGED_CELLS": str(self.table_duplicate_text_in_merged_cells),
                "HIDE_FOOTER_LAYOUT": str(self.hide_footer_layout),
                "HIDE_HEADER_LAYOUT": str(self.hide_header_layout),
                "HIDE_PAGE_NUM_LAYOUT": str(self.hide_page_num_layout),
                "USE_TABLE": str(self.use_table),
            },
            role=self.lambda_textract_role,
            layers=self.textract_only_code_layers,
        )
        self.textract_lambda.add_alias(
            "Warm",
            provisioned_concurrent_executions=0,
            description="Alias used for Lambda provisioned concurrency",
        )

    ## **************** IAM Permissions ****************
    def create_roles(self: str):
        ## ********* IAM Roles *********
        self.lambda_attributes_role = iam.Role(
            self,
            f"{self.stack_name}-attributes-role",
            role_name=f"{self.stack_name}-attributes-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
            ),
        )
        self.lambda_presigned_url_role = iam.Role(
            self,
            f"{self.stack_name}-presigned-url-role",
            role_name=f"{self.stack_name}-presigned-url-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
            ),
        )
        self.lambda_textract_role = iam.Role(
            self,
            f"{self.stack_name}-textract-role",
            role_name=f"{self.stack_name}-textract-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
            ),
        )
        self.lambda_retrieve_examples_role = iam.Role(
            self,
            f"{self.stack_name}-retrieve-examples-role",
            role_name=f"{self.stack_name}-retrieve-examples-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
            ),
        )
        ## ********* Cloudwatch *********
        cloudwatch_access_docpolicy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=["*"],
                )
            ]
        )
        self.cloudwatch_access_policy = iam.Policy(
            self,
            f"{self.stack_name}-cloudwatch-access-policy",
            policy_name=f"{self.stack_name}-cloudwatch-access-policy",
            document=cloudwatch_access_docpolicy,
        )
        self.lambda_presigned_url_role.attach_inline_policy(self.cloudwatch_access_policy)
        self.lambda_textract_role.attach_inline_policy(self.cloudwatch_access_policy)
        self.lambda_attributes_role.attach_inline_policy(self.cloudwatch_access_policy)
        self.lambda_retrieve_examples_role.attach_inline_policy(self.cloudwatch_access_policy)

        # Added to suppressing list given Resource::arn:aws:logs:<AWS::Region>:<AWS::AccountId>:log-group:*
        self.nag_suppressed_resources.append(self.cloudwatch_access_policy)

        ## ********* DynamoDB *********
        ddb_docpolicy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:PutItem",
                        "dynamodb:GetItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:Query",
                        "dynamodb:UpdateItem",
                        "dynamodb:Scan",
                    ],
                    resources=[
                        self.few_shots_table.table_arn,
                    ],
                )
            ]
        )
        ddb_policy = iam.Policy(
            self,
            f"{self.stack_name}-model-params-db-policy",
            policy_name=f"{self.stack_name}-model-params-db-policy",
            document=ddb_docpolicy,
        )
        self.lambda_attributes_role.attach_inline_policy(ddb_policy)
        self.lambda_retrieve_examples_role.attach_inline_policy(ddb_policy)

        ## ********* Textract *********
        textract_access_docpolicy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "textract:StartDocumentTextDetection",
                        "textract:StartDocumentAnalysis",
                        "textract:GetDocumentTextDetection",
                        "textract:GetDocumentAnalysis",
                        "textract:DetectDocumentText",
                        "textract:AnalyzeDocument",
                    ],
                    resources=["*"],
                )
            ]
        )
        textract_access_policy = iam.Policy(
            self,
            f"{self.stack_name}-textract-access-policy",
            policy_name=f"{self.stack_name}-textract-access-policy",
            document=textract_access_docpolicy,
        )
        self.lambda_textract_role.attach_inline_policy(textract_access_policy)
        self.nag_suppressed_resources.append(textract_access_policy)

        ## ********* Bedrock *********
        bedrock_access_docpolicy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream",
                        "bedrock:ListBlueprints",
                        "bedrock:CreateBlueprint",
                        "bedrock:UpdateBlueprint",
                        "bedrock:InvokeDataAutomationAsync",
                        "bedrock:GetDataAutomationStatus",
                    ],
                    resources=["*"],
                )
            ]
        )
        bedrock_access_policy = iam.Policy(
            self,
            f"{self.stack_name}-bedrock-access-policy",
            policy_name=f"{self.stack_name}-bedrock-access-policy",
            document=bedrock_access_docpolicy,
        )
        self.lambda_attributes_role.attach_inline_policy(bedrock_access_policy)
        # Added to suppressing list given we should provide customers access to all models by default
        self.nag_suppressed_resources.append(bedrock_access_policy)

        ## ********* S3 *********
        if self.s3_kms_key:
            kms_policy = iam.Policy(
                self,
                f"{self.stack_name}-api-s3-kms-policy",
                policy_name=f"{self.stack_name}-api-s3-kms-policy",
                document=iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "kms:DescribeKey",
                                "kms:GenerateDataKey",
                                "kms:ReEncrypt",
                                "kms:Decrypt",
                                "kms:Encrypt",
                            ],
                            resources=[self.s3_kms_key.key_arn],
                        )
                    ]
                ),
            )
            self.lambda_attributes_role.attach_inline_policy(kms_policy)

        ## ********* S3 *********
        s3_read_write_files_document = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=["s3:GetObject*", "s3:GetBucket*", "s3:List*", "s3:PutObject*", "s3:DeleteObject*"],
                    resources=[self.s3_data_bucket.bucket_arn, self.s3_data_bucket.bucket_arn + "/*"],
                    effect=iam.Effect.ALLOW,
                ),
            ]
        )
        self.s3_read_write_files_policy = iam.Policy(
            self, f"{self.stack_name}-s3-read-write-policy", document=s3_read_write_files_document
        )
        self.nag_suppressed_resources.append(self.s3_read_write_files_policy)
        self.lambda_attributes_role.attach_inline_policy(self.s3_read_write_files_policy)
        self.lambda_presigned_url_role.attach_inline_policy(self.s3_read_write_files_policy)
        self.lambda_textract_role.attach_inline_policy(self.s3_read_write_files_policy)

    def create_stepfunction_role(self: str):
        ## ********* IAM Roles *********
        self.stepfunctions_role = iam.Role(
            self,
            f"{self.stack_name}-stepfunctions-role",
            role_name=f"{self.stack_name}-stepfunctions-role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("states.amazonaws.com"),
            ),
        )

        ## ********* S3 *********
        self.stepfunctions_role.attach_inline_policy(self.s3_read_write_files_policy)

        ## ********* Lambda invocation *********
        lambda_invocation_docpolicy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=["Lambda:InvokeFunction"],
                    resources=[
                        self.attributes_lambda.function_arn,
                        self.textract_lambda.function_arn,
                        self.read_office_lambda.function_arn,
                        self.llm_attributes_lambda.function_arn,
                        self.bda_lambda.function_arn,
                    ],
                )
            ]
        )
        lambda_invocation_policy = iam.Policy(
            self,
            f"{self.stack_name}-lambda-invocation-policy",
            policy_name=f"{self.stack_name}-lambda-invocation-policy",
            document=lambda_invocation_docpolicy,
        )
        self.stepfunctions_role.attach_inline_policy(lambda_invocation_policy)
        self.nag_suppressed_resources.append(self.stepfunctions_role)

    ## **************** Step Functions ****************
    def create_stepfunctions(self):
        # Update log group with vendedlogs prefix
        log_group = logs.LogGroup(
            self,
            f"{self.stack_name}/StepFunctions",
            log_group_name=f"/aws/vendedlogs/states/{self.stack_name}/stepfunctions",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.TWO_WEEKS,
        )

        self.idp_bedrock_state_machine = sfn.StateMachine(
            scope=self,
            id=f"{self.stack_name}-StepFunctions",
            definition_body=sfn.DefinitionBody.from_file("assets/state_machine/idp_bedrock.json"),
            definition_substitutions={
                "LAMBDA_READ_OFFICE": self.read_office_lambda.function_arn,
                "LAMBDA_RUN_TEXTRACT": self.textract_lambda.function_arn,
                "LAMBDA_RUN_BDA": self.bda_lambda.function_arn,
                "LAMBDA_EXTRACT_ATTRIBUTES": self.attributes_lambda.function_arn,
                "LAMBDA_EXTRACT_ATTRIBUTES_LLM": self.llm_attributes_lambda.function_arn,
            },
            role=self.stepfunctions_role,
            state_machine_name=f"{self.stack_name}-StepFunctions",
            tracing_enabled=True,
            logs=sfn.LogOptions(destination=log_group, level=sfn.LogLevel.ALL),
        )

    ## **************** CDK NAG suppressions ****************
    def add_nag_suppressions(self):
        NagSuppressions.add_resource_suppressions(
            self.nag_suppressed_resources,
            [
                NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason="All IAM policies defined in this solution grant only least-privilege permissions. Wild card for resources is used only for services which do not have a resource arn",  # noqa: E501
                )
            ],
            apply_to_children=True,
        )
