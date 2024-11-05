"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    IDP Bedrock stack
"""

import json
from typing import Any, Dict

import aws_cdk.aws_apigateway as apigw_v1
from aws_cdk import Aws, RemovalPolicy, Stack, Tags
from aws_cdk import CfnOutput as output
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as _s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from infra.constructs.idp_bedrock_api import IDPBedrockAPIConstructs
from infra.constructs.idp_bedrock_buckets import ServerAccessLogsBucket
from infra.constructs.idp_bedrock_layers import IDPBedrockLambdaLayers
from infra.stacks.idp_bedrock_streamlit import IDPBedrockStreamlitStack

DEPLOY_DEV_INDEX = False  # If True an extra Kendra for development is deployed


class IDPBedrockStack(Stack):
    """
    IDP Bedrock stack
    """

    def __init__(self, scope: Construct, stack_name: str, config: Dict[str, Any], **kwargs) -> None:  # noqa: C901
        description = "IDP Bedrock (uksb-0rxb2u6bob)"
        super().__init__(scope, stack_name, description=description, **kwargs)

        ## Set architecture and Python Runtime
        architecture = config["lambda"].get("architecture", "X86_64")
        python_runtime = config["lambda"].get("python_runtime", "PYTHON_3_11")

        if architecture == "ARM_64":
            self._architecture = _lambda.Architecture.ARM_64
        elif architecture == "X86_64":
            self._architecture = _lambda.Architecture.X86_64
        else:
            raise RuntimeError("Select one option for system architecture among [ARM_64, X86_64]")

        if python_runtime == "PYTHON_3_9":
            self._runtime = _lambda.Runtime.PYTHON_3_9
        elif python_runtime == "PYTHON_3_10":
            self._runtime = _lambda.Runtime.PYTHON_3_10
        elif python_runtime == "PYTHON_3_11":
            self._runtime = _lambda.Runtime.PYTHON_3_11
        elif python_runtime == "PYTHON_3_12":
            self._runtime = _lambda.Runtime.PYTHON_3_12
        else:
            raise RuntimeError("Select a Python version >= PYTHON_3_9")

        ## ** Create logging bucket for server access logs **
        s3_logs_bucket = ServerAccessLogsBucket(self, f"{stack_name}-LOGS-BUCKET", stack_name=stack_name)

        ## **************** Create S3 Bucket ****************

        if config["s3"]["encryption"] == "SSE-KMS":
            if config["s3"]["kms_key_arn"] != "None":
                self.s3_kms_key = kms.Key.from_key_arn(
                    self,
                    f"{stack_name}-s3-key",
                    key_arn=config["s3"]["kms_key_arn"],
                )
            else:
                self.s3_kms_key = kms.Key(
                    self,
                    f"{stack_name}-s3-key",
                    alias=f"{stack_name}-s3-key",
                    enabled=True,
                    enable_key_rotation=True,
                    key_spec=kms.KeySpec.SYMMETRIC_DEFAULT,
                    key_usage=kms.KeyUsage.ENCRYPT_DECRYPT,
                )
            bucket_key_enabled = True
            encryption = _s3.BucketEncryption.KMS
        else:
            bucket_key_enabled = False
            encryption = _s3.BucketEncryption.S3_MANAGED
            self.s3_kms_key = None

        if config["s3"]["use_existing_bucket"]:
            self.s3_data_bucket = _s3.Bucket.from_bucket_name(
                self, id=f"{stack_name}-data", bucket_name=config["s3"]["bucket_name"]
            )
        else:
            data_bucket_name = f"{stack_name.lower()}-data-{Aws.ACCOUNT_ID}"
            self.s3_data_bucket = _s3.Bucket(
                self,
                id=f"{stack_name}-data",
                bucket_name=data_bucket_name,
                block_public_access=_s3.BlockPublicAccess.BLOCK_ALL,
                removal_policy=RemovalPolicy.DESTROY,
                bucket_key_enabled=bucket_key_enabled,
                server_access_logs_bucket=s3_logs_bucket.bucket,
                server_access_logs_prefix=f"buckets/{data_bucket_name}",
                encryption=encryption,
                enforce_ssl=True,
            )

        ## **************** Lambda layers ****************

        self.layers = IDPBedrockLambdaLayers(
            self,
            f"{stack_name}-layers",
            stack_name=stack_name,
            architecture=self._architecture,
            python_runtime=self._runtime,
        )

        ## ********** Bedrock configs ***********
        bedrock_region = kwargs["env"].region
        textract_region = kwargs["env"].region

        if "bedrock" in config:
            if "region" in config["bedrock"]:
                bedrock_region = (
                    kwargs["env"].region if config["bedrock"]["region"] == "None" else config["bedrock"]["region"]
                )
        if "textract" in config:
            if "region" in config["textract"]:
                textract_region = (
                    kwargs["env"].region if config["textract"]["region"] == "None" else config["textract"]["region"]
                )

        ## ********** Textract configs ***********

        if "textract" in config:
            if "table_flatten_headers" in config["textract"]:
                table_flatten_headers = config["textract"]["table_flatten_headers"]
            if "table_remove_column_headers" in config["textract"]:
                table_remove_column_headers = config["textract"]["table_remove_column_headers"]
            if "table_duplicate_text_in_merged_cells" in config["textract"]:
                table_duplicate_text_in_merged_cells = config["textract"]["table_duplicate_text_in_merged_cells"]
            if "hide_footer_layout" in config["textract"]:
                hide_footer_layout = config["textract"]["hide_footer_layout"]
            if "hide_header_layout" in config["textract"]:
                hide_header_layout = config["textract"]["hide_header_layout"]
            if "hide_page_num_layout" in config["textract"]:
                hide_page_num_layout = config["textract"]["hide_page_num_layout"]
            if "use_table" in config["textract"]:
                use_table = config["textract"]["use_table"]

        ## ********** Authentication configs ***********
        mfa_enabled = config.get("authentication", {}).get("MFA", True)
        access_token_validity = config.get("authentication", {}).get("access_token_validity", 60)

        ## **************** API Constructs  ****************
        ## ******* Enable API Gateway logging *******
        # There should be only one AWS::ApiGateway::Account resource per region per account
        cloud_watch_role = iam.Role(
            self,
            "ApiGatewayCloudWatchLoggingRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonAPIGatewayPushToCloudWatchLogs")
            ],
        )
        apigw_account = apigw_v1.CfnAccount(self, "ApiGatewayAccount", cloud_watch_role_arn=cloud_watch_role.role_arn)

        self.api_constructs = IDPBedrockAPIConstructs(
            self,
            f"{stack_name}-API",
            stack_name=stack_name,
            s3_data_bucket=self.s3_data_bucket,
            s3_kms_key=self.s3_kms_key,
            layers=self.layers,
            bedrock_region=bedrock_region,
            textract_region=textract_region,
            table_flatten_headers=table_flatten_headers,
            table_remove_column_headers=table_remove_column_headers,
            table_duplicate_text_in_merged_cells=table_duplicate_text_in_merged_cells,
            hide_footer_layout=hide_footer_layout,
            hide_header_layout=hide_header_layout,
            hide_page_num_layout=hide_page_num_layout,
            use_table=use_table,
            mfa_enabled=mfa_enabled,
            access_token_validity=access_token_validity,
            architecture=self._architecture,
            python_runtime=self._runtime,
        )

        self.api_constructs.node.add_dependency(apigw_account)

        ## **************** Set SSM Parameters ****************
        # Note: StringParameter name cannot start with "aws".
        self.ssm_cover_image_url = ssm.StringParameter(
            self,
            f"{stack_name}-SsmCoverImageUrl",
            parameter_name=f"/{stack_name}/ecs/COVER_IMAGE_URL",
            string_value=config["streamlit"]["cover_image_url"],
        )
        self.ssm_assistant_avatar_url = ssm.StringParameter(
            self,
            f"{stack_name}-SsmAssistantAvatarUrl",
            parameter_name=f"/{stack_name}/ecs/ASSISTANT_AVATAR_URL",
            string_value=config["streamlit"]["assistant_avatar"],
        )
        self.ssm_bedrock_model_ids = ssm.StringParameter(
            self,
            f"{stack_name}-SsmBedrockModelIds",
            parameter_name=f"/{stack_name}/ecs/BEDROCK_MODEL_IDS",
            string_value=json.dumps(config["bedrock"].get("model_ids", [])),
        )
        self.ssm_region = ssm.StringParameter(
            self,
            f"{stack_name}-SsmRegion",
            parameter_name=f"/{stack_name}/ecs/REGION",
            string_value=self.region,
        )

        ## **************** S3 BUCKET ****************

        self.ssm_bucket_name = ssm.StringParameter(
            self,
            f"{stack_name}-SsmBucketName",
            parameter_name=f"/{stack_name}/ecs/BUCKET_NAME",
            string_value=self.s3_data_bucket.bucket_name,
        )

        ## **************** Streamlit NestedStack ****************
        if config["streamlit"]["deploy_streamlit"]:
            self.streamlit_constructs = IDPBedrockStreamlitStack(
                self,
                f"{stack_name}-STREAMLIT",
                stack_name=stack_name,
                s3_data_bucket=self.s3_data_bucket,
                s3_logs_bucket=s3_logs_bucket.bucket,
                ecs_cpu=config["streamlit"]["ecs_cpu"],
                ecs_memory=config["streamlit"]["ecs_memory"],
                open_to_public_internet=config["streamlit"]["open_to_public_internet"],
                ip_address_allowed=config["streamlit"].get("ip_address_allowed"),
                ssm_client_id=self.api_constructs.ssm_client_id,
                ssm_user_pool_id=self.api_constructs.ssm_user_pool_id,
                ssm_region=self.ssm_region,
                ssm_api_uri=self.api_constructs.ssm_api_uri,
                ssm_bucket_name=self.ssm_bucket_name,
                ssm_cover_image_url=self.ssm_cover_image_url,
                ssm_bedrock_model_ids=self.ssm_bedrock_model_ids,
                ssm_assistant_avatar_url=self.ssm_assistant_avatar_url,
                ssm_state_machine_arn=self.api_constructs.ssm_state_machine_arn,
                state_machine_name=self.api_constructs.idp_bedrock_state_machine.state_machine_name,
            )

            self.cloudfront_distribution_name = output(
                self,
                id="CloudfrontDistributionName",
                value=self.streamlit_constructs.cloudfront.domain_name,
            )

        ## **************** Tags ****************
        Tags.of(self).add("StackName", stack_name)
        Tags.of(self).add("Team", "GenAIIC")
