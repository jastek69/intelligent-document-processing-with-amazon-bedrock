"""
Copyright © Amazon.com and Affiliates
"""

import os
from pathlib import Path

from aws_cdk import Duration
from aws_cdk import Aws, NestedStack, RemovalPolicy, Tags
from aws_cdk import CfnOutput as output
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk.aws_cloudfront import FunctionEventType
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as _s3
from aws_cdk import aws_ssm as ssm

# from aws_cdk import custom_resources as cr
from aws_cdk.aws_cloudfront_origins import LoadBalancerV2Origin
from aws_cdk.aws_ecr_assets import DockerImageAsset
from cdk_nag import NagPackSuppression, NagSuppressions
from constructs import Construct


class CloudWatchLogGroup(Construct):
    ALLOWED_WRITE_ACTIONS = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
    ]

    def __init__(self, scope: Construct, id: str, resource_prefix: str, log_group_name: str) -> None:
        super().__init__(scope, id)
        self.log_group = logs.LogGroup(
            self,
            "FrontEndLogGroup",
            log_group_name=log_group_name,
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.TWO_WEEKS,
        )

        self._write_policies = []
        self._write_policies.append(
            iam.Policy(
                scope=self,
                id="CloudWatchLogsWritePolicy",
                policy_name=f"{resource_prefix}-logs-w-policy",
                statements=[
                    iam.PolicyStatement(
                        actions=self.ALLOWED_WRITE_ACTIONS, effect=iam.Effect.ALLOW, resources=[f"{self.arn}/*"]
                    ),
                ],
            )
        )

    def grant_write(self, role: iam.IRole) -> None:
        for policy in self._write_policies:
            role.attach_inline_policy(policy=policy)

    @property
    def arn(self) -> str:
        return self.log_group.log_group_arn


class IDPBedrockECSStack(NestedStack):
    ALLOWED_ECR_AUTHENTICATION_ACTIONS = [
        "ecr:GetAuthorizationToken",
    ]
    ALLOWED_ECR_READ_ACTIONS = [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
    ]

    def __init__(
        self,
        scope: Construct,
        id: str,
        stack_name: str,
        state_machine_name: str,
        s3_data_bucket: _s3.Bucket,
        s3_logs_bucket: _s3.Bucket,
        ecs_cpu: int = 512,
        ecs_memory: int = 1024,
        ssm_client_id=None,
        ssm_cognito_domain=None,
        ssm_user_pool_id: ssm.StringParameter = None,
        ssm_region: ssm.StringParameter = None,
        ssm_api_uri=None,
        ssm_bucket_name=None,
        ssm_cover_image_url=None,
        ssm_bedrock_model_ids=None,
        ssm_assistant_avatar_url=None,
        ssm_state_machine_arn=None,
        open_to_public_internet=False,
        ip_address_allowed: list = None,
        # enable_waf: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, description="Frontend for IDP with Amazon Bedrock", **kwargs)
        # self.env = "dev"
        self.prefix = stack_name
        self.ecs_cpu = ecs_cpu
        self.ecs_memory = ecs_memory
        self.ip_address_allowed = ip_address_allowed
        self.s3_data_bucket = s3_data_bucket
        self.s3_logs_bucket = s3_logs_bucket
        # self.enable_waf = enable_waf
        self.ssm_client_id = ssm_client_id
        self.ssm_user_pool_id = ssm_user_pool_id
        self.ssm_region = ssm_region
        self.ssm_api_uri = ssm_api_uri
        self.ssm_bucket_name = ssm_bucket_name
        self.ssm_cover_image_url = ssm_cover_image_url
        self.ssm_bedrock_model_ids = ssm_bedrock_model_ids
        self.ssm_assistant_avatar_url = ssm_assistant_avatar_url
        self.ssm_state_machine_arn = ssm_state_machine_arn
        self.state_machine_name = state_machine_name
        self.ssm_cognito_domain = ssm_cognito_domain
        self.nag_suppressed_resources = []
        self.docker_asset = self.build_docker_push_ecr()

        # Name and value of the custom header to be used for authentication
        self.custom_header_name = f"{stack_name}-{Aws.ACCOUNT_ID}-cf-header"
        self.custom_header_value = self.docker_asset.asset_hash

        self.vpc = self.create_webapp_vpc(open_to_public_internet=open_to_public_internet)

        self.cluster, self.alb, self.cloudfront = self.create_ecs_and_alb(
            open_to_public_internet=open_to_public_internet
        )

        NagSuppressions.add_stack_suppressions(
            self,
            apply_to_nested_stacks=True,
            suppressions=[
                NagPackSuppression(
                    **{
                        "id": "AwsSolutions-IAM5",
                        "reason": "Access to all log groups required for CloudWatch log group creation.",
                    }
                ),
            ],
        )
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

        # Add to hosted UI in Cognito Console:
        #   https://idp_bedrock.click
        #   https://idp_bedrock.click/oauth2/idpresponse

        # self.alb_dns_name = output(self, id="AlbDnsName", value=self.alb.load_balancer_dns_name)
        self.cloudfront_distribution_name = output(
            self, id="CloudfrontDistributionName", value=self.cloudfront.domain_name
        )
        ## **************** Tags ****************
        Tags.of(self).add("StackName", id)
        Tags.of(self).add("Team", "GAIIC")

    def build_docker_push_ecr(self):
        # ECR: Docker build and push to ECR
        return DockerImageAsset(
            self,
            "ECSImg",
            # asset_name = f"{prefix}-streamlit-img",
            directory=os.path.join(Path(__file__).parent.parent.parent, "src/ecs"),
        )

    def create_webapp_vpc(self, open_to_public_internet=False):
        # VPC for ALB and ECS cluster
        vpc = ec2.Vpc(
            self,
            "WebappVpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            vpc_name=f"{self.prefix}-stl-vpc",
            nat_gateways=1,
        )

        ec2.FlowLog(self, "WebappVpcFlowLog", resource_type=ec2.FlowLogResourceType.from_vpc(vpc))

        self.ecs_security_group = ec2.SecurityGroup(
            self,
            "SecurityGroupECS",
            vpc=vpc,
            security_group_name=f"{self.prefix}-stl-ecs-sg",
        )
        self.ecs_security_group.add_ingress_rule(
            peer=self.ecs_security_group,
            connection=ec2.Port.all_traffic(),
            description="Within Security Group",
        )

        self.alb_security_group = ec2.SecurityGroup(
            self,
            "SecurityGroupALB",
            vpc=vpc,
            security_group_name=f"{self.prefix}-stl-alb-sg",
        )
        self.alb_security_group.add_ingress_rule(
            peer=self.alb_security_group,
            connection=ec2.Port.all_traffic(),
            description="Within Security Group",
        )

        if self.ip_address_allowed:
            for ip in self.ip_address_allowed:
                if ip.startswith("pl-"):
                    _peer = ec2.Peer.prefix_list(ip)
                    # cf https://apll.tools.aws.dev/#/
                else:
                    _peer = ec2.Peer.ipv4(ip)
                    # cf https://dogfish.amazon.com/#/search?q=Unfabric&attr.scope=PublicIP
                self.alb_security_group.add_ingress_rule(
                    peer=_peer,
                    connection=ec2.Port.tcp(80),
                )

        # Change IP address to developer IP for testing
        # self.alb_security_group.add_ingress_rule(peer=ec2.Peer.ipv4("1.2.3.4/32"),
        # connection=ec2.Port.tcp(443), description = "Developer IP")

        self.ecs_security_group.add_ingress_rule(
            peer=self.alb_security_group,
            connection=ec2.Port.tcp(8501),
            description="ALB traffic",
        )

        # Add rule to allow traffic from CloudFront to ALB
        self.alb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4("130.176.0.0/16"),  # CloudFront IP range
            connection=ec2.Port.tcp(80),
            description="Allow CloudFront traffic",
        )

        # Add other CloudFront IP ranges
        for ip_range in [
            "15.158.0.0/16",
            "130.176.0.0/16",
            "15.188.0.0/16",
            "130.176.0.0/16",
            "108.156.0.0/14",
            "120.52.0.0/16",
            "205.251.208.0/20",
            "180.163.57.0/24",
            "204.246.164.0/22",
            "54.192.0.0/16",
        ]:
            self.alb_security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(ip_range),
                connection=ec2.Port.tcp(80),
                description=f"Allow CloudFront traffic from {ip_range}",
            )

        return vpc

    def grant_ecr_read_access(self, role: iam.IRole) -> None:
        policy = iam.Policy(
            scope=self,
            id="CloudWatchEcrReadPolicy",
            policy_name=f"{self.resource_prefix}-ecr-r-policy",
            statements=[
                iam.PolicyStatement(
                    actions=self.ALLOWED_ECR_AUTHENTICATION_ACTIONS, effect=iam.Effect.ALLOW, resources=["*"]
                ),
                iam.PolicyStatement(actions=self.ALLOWED_ECR_READ_ACTIONS, effect=iam.Effect.ALLOW, resources=["*"]),
            ],
        )
        role.attach_inline_policy(policy=policy)

    def create_ecs_and_alb(self, open_to_public_internet=False):
        # ECS cluster and service definition

        cluster = ecs.Cluster(
            self,
            "Cluster",
            enable_fargate_capacity_providers=True,
            vpc=self.vpc,
            container_insights=True,
        )

        alb_suffix = "" if open_to_public_internet else "-priv"

        # ALB to connect to ECS
        load_balancer_name = f"{self.prefix}-stl{alb_suffix}"
        alb = elbv2.ApplicationLoadBalancer(
            self,
            f"{self.prefix}-alb{alb_suffix}",
            vpc=self.vpc,
            internet_facing=open_to_public_internet,
            load_balancer_name=load_balancer_name,
            security_group=self.alb_security_group,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        service_logs_prefix = f"load-balancers/{load_balancer_name}"
        # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-elasticloadbalancingv2-loadbalancer-loadbalancerattribute.html

        alb.log_access_logs(bucket=self.s3_logs_bucket, prefix=service_logs_prefix)

        self.resource_prefix = f"{self.prefix}-frontend-container"

        log_group = CloudWatchLogGroup(
            scope=self,
            id="ECSContainerLogGroup",
            resource_prefix=self.resource_prefix,
            log_group_name=f"/{self.prefix}/ecs",
        )

        task_execution_role = iam.Role(
            self,
            "WebContainerTaskExecutionRole",
            role_name=f"{self.resource_prefix}-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        log_group.grant_write(role=task_execution_role)
        self.grant_ecr_read_access(role=task_execution_role)

        # Add Step Functions access
        step_functions_docpolicy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "states:StartSyncExecution",
                        "states:StartExecution",
                        "states:DescribeExecution",
                    ],
                    resources=[
                        f"arn:aws:states:{Aws.REGION}:{Aws.ACCOUNT_ID}:execution:{self.state_machine_name}:*",
                        f"arn:aws:states:{Aws.REGION}:{Aws.ACCOUNT_ID}:stateMachine:{self.state_machine_name}",
                    ],
                )
            ]
        )
        step_functions_policy = iam.Policy(
            self,
            "StepFunctionsPolicy",
            policy_name=f"{self.resource_prefix}-stepfunctions-access",
            document=step_functions_docpolicy,
        )
        task_execution_role.attach_inline_policy(step_functions_policy)

        # Add S3 access
        s3_docpolicy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "s3:GetObject*",
                        "s3:GetBucket*",
                        "s3:List*",
                        "s3:PutObject*",
                        "s3:DeleteObject*",
                        "s3:GetObject",
                        "s3:ListBucket",
                    ],
                    resources=[self.s3_data_bucket.bucket_arn, self.s3_data_bucket.bucket_arn + "/*"],
                    effect=iam.Effect.ALLOW,
                ),
            ]
        )
        s3_policy = iam.Policy(
            self,
            "S3Policy",
            policy_name=f"{self.stack_name}-s3-access",
            document=s3_docpolicy,
        )
        # Added to suppressing list given we should provide customers access to all models by default
        self.nag_suppressed_resources.append(s3_policy)
        task_execution_role.attach_inline_policy(s3_policy)

        ecs_log_driver = ecs.LogDrivers.aws_logs(
            stream_prefix="AwsLogsLogDriver", log_group=log_group.log_group
        )  # Full log stream name: [PREFIX]/[CONTAINER-NAME]/[ECS-TASK-ID]

        # TODO add WAF support
        # ********* WAF *********
        # Instantiate a WAF if needed
        # Add the waf to the cloudfront distribution

        """
        if self.enable_waf:
            waf = wafv2.CfnWebACL(self,
                'ECSWAF',
                default_action= {
                    'allow': {}
                },
                scope= 'CLOUDFRONT',
                visibility_config = {
                    'cloudWatchMetricsEnabled' : True,
                    'metricName' : 'MetricForWebACLCDK',
                    'sampledRequestsEnabled' : True,
                },
                name= f"{self.prefix}-stl-waf",
                rules= [wafv2.CfnWebACL.RuleProperty(
                    name = 'CRSRule',
                    priority= 0,
                    statement= wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement= {
                            'name' : 'AWSManagedRulesCommonRuleSet',
                            'vendorName':'AWS'
                    }),
                    visibility_config= {
                        'cloudWatchMetricsEnabled': True,
                        'metricName':'MetricForWebACLCDK-CRS',
                        'sampledRequestsEnabled': True,
                    },

                )]
            )
            waf_arn = waf.attr_arn
        else:
            waf_arn = None
        """

        # ********* Cloudfront distribution *********

        # Update the CloudFront function to rewrite /oauth2/idpresponse to /
        # Update the CloudFront function to properly handle /oauth2/idpresponse and pass the code to ECS
        function = cloudfront.Function(
            self,
            "RedirectFunction",
            code=cloudfront.FunctionCode.from_inline(f"""
            function handler(event) {{
                var request = event.request;
                var uri = request.uri;

                // If this is the callback endpoint with a code, redirect to root
                if (uri.startsWith('/oauth2/idpresponse') && request.querystring.code) {{
                    return {{
                        statusCode: 302,
                        statusDescription: 'Found',
                        headers: {{
                            'location': {{
                                value: '/?code=' + request.querystring.code.value
                            }},
                            'cache-control': {{
                                value: 'no-cache, no-store, must-revalidate'
                            }}
                        }}
                    }};
                }}

                // If the request is to '/' and has a code, allow it to pass through
                if (request.querystring.code) {{
                    return request;
                }}

                // Allow specific resource paths to pass through regardless of query parameters
                var allowed_paths = [
                    '/static/',
                    '/_stcore/',
                    '/favicon.ico',
                    '/robots.txt',
                    '/app/'
                    // Add more paths as needed
                ];

                for (var i = 0; i < allowed_paths.length; i++) {{
                    if (uri.startsWith(allowed_paths[i])) {{
                        return request;
                    }}
                }}

                // If no code, redirect to Cognito
                if (uri === '/') {{
                    var cognitoUrl = 'https://{self.prefix}-{Aws.ACCOUNT_ID}.auth.{Aws.REGION}.amazoncognito.com/oauth2/authorize';
                    cognitoUrl += '?client_id={self.ssm_client_id.string_value}';
                    cognitoUrl += '&response_type=code';
                    cognitoUrl += '&scope=openid+profile+email';
                    cognitoUrl += '&redirect_uri=https://' + request.headers.host.value + '/oauth2/idpresponse';

                    return {{
                        statusCode: 302,
                        statusDescription: 'Found',
                        headers: {{
                            'location': {{ value: cognitoUrl }},
                            'cache-control': {{ value: 'no-cache, no-store, must-revalidate' }}
                        }}
                    }};
                }}

                return request;
            }}
            """),
        )

        # Create the CloudFront distribution with redirect behavior
        distribution_name = f"{self.prefix}-cf-dist"
        cloudfront_distribution = cloudfront.Distribution(
            self,
            distribution_name,
            comment=self.prefix,
            default_behavior=cloudfront.BehaviorOptions(
                origin=LoadBalancerV2Origin(
                    alb,
                    custom_headers={self.custom_header_name: self.custom_header_value},
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
                    http_port=80,
                    connection_attempts=3,
                    connection_timeout=Duration.seconds(10),
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                function_associations=[
                    cloudfront.FunctionAssociation(function=function, event_type=FunctionEventType.VIEWER_REQUEST)
                ],
            ),
            enable_logging=True,
            log_bucket=self.s3_logs_bucket,
            log_file_prefix=f"distributions/{distribution_name}",
            # default_root_object="oauth2/authorize",
        )

        self.ssm_cloudfront_domain = ssm.StringParameter(
            self,
            f"{self.prefix}-SsmCloudFront",
            parameter_name=f"/{self.prefix}/ecs/CLOUDFRONT_DOMAIN",
            string_value=f"{cloudfront_distribution.domain_name}",
        )

        # Create Fargate task definition AFTER creating SSM parameters
        fargate_task_definition = ecs.FargateTaskDefinition(
            self,
            "WebappTaskDef",
            memory_limit_mib=self.ecs_memory,
            cpu=self.ecs_cpu,
            execution_role=task_execution_role,
            task_role=task_execution_role,
        )

        # Add container with the secrets
        fargate_task_definition.add_container(
            "ECSAppContainer",
            image=ecs.ContainerImage.from_docker_image_asset(self.docker_asset),
            port_mappings=[ecs.PortMapping(container_port=8501, protocol=ecs.Protocol.TCP)],
            secrets={
                "CLIENT_ID": ecs.Secret.from_ssm_parameter(self.ssm_client_id),
                "USER_POOL_ID": ecs.Secret.from_ssm_parameter(self.ssm_user_pool_id),
                "REGION": ecs.Secret.from_ssm_parameter(self.ssm_region),
                "API_URI": ecs.Secret.from_ssm_parameter(self.ssm_api_uri),
                "BUCKET_NAME": ecs.Secret.from_ssm_parameter(self.ssm_bucket_name),
                "COVER_IMAGE_URL": ecs.Secret.from_ssm_parameter(self.ssm_cover_image_url),
                "ASSISTANT_AVATAR_URL": ecs.Secret.from_ssm_parameter(self.ssm_assistant_avatar_url),
                "BEDROCK_MODEL_IDS": ecs.Secret.from_ssm_parameter(self.ssm_bedrock_model_ids),
                "STATE_MACHINE_ARN": ecs.Secret.from_ssm_parameter(self.ssm_state_machine_arn),
                "COGNITO_DOMAIN": ecs.Secret.from_ssm_parameter(self.ssm_cognito_domain),
                "CLOUDFRONT_DOMAIN": ecs.Secret.from_ssm_parameter(self.ssm_cloudfront_domain),
            },
            logging=ecs_log_driver,
        )

        service = ecs.FargateService(
            self,
            "ECSService",
            cluster=cluster,
            task_definition=fargate_task_definition,
            service_name=f"{self.prefix}-stl-front",
            security_groups=[self.ecs_security_group],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # ********* ALB Listener *********

        http_listener = alb.add_listener(
            f"{self.prefix}-http-listener{alb_suffix}",
            port=80,
            default_action=elbv2.ListenerAction.fixed_response(
                status_code=403, content_type="text/plain", message_body="Access denied"
            ),  # Default deny all traffic
        )

        # Add target group with custom header validation
        http_listener.add_action(
            "allow-cloudfront",
            conditions=[elbv2.ListenerCondition.http_header(self.custom_header_name, [self.custom_header_value])],
            priority=1,
            action=elbv2.ListenerAction.forward(
                target_groups=[
                    elbv2.ApplicationTargetGroup(  # Modify this target group configuration
                        self,
                        f"{self.prefix}-tg{alb_suffix}",
                        vpc=self.vpc,
                        port=8501,
                        protocol=elbv2.ApplicationProtocol.HTTP,
                        targets=[service],
                        target_group_name=f"{self.prefix}-tg{alb_suffix}",
                        health_check={  # Add this health check configuration
                            "path": "/_stcore/health",
                            "port": "8501",
                            "protocol": elbv2.Protocol.HTTP,
                            "interval": Duration.seconds(30),
                            "timeout": Duration.seconds(5),
                            "healthy_threshold_count": 2,
                            "unhealthy_threshold_count": 5,
                        },
                    )
                ]
            ),
        )

        return cluster, alb, cloudfront_distribution
