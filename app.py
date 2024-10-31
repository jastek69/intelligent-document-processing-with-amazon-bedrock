"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
Package content:
    Entry point of the CDK application
"""

import os
from pathlib import Path

import aws_cdk as cdk
import yaml
from cdk_nag import AwsSolutionsChecks, NagSuppressions
from yaml.loader import SafeLoader

from infra.idp_bedrock_stack import IDPBedrockStack

with open(os.path.join(Path(__file__).parent, "config.yml"), "r", encoding="utf-8") as yaml_file:
    stack_config = yaml.load(yaml_file, Loader=SafeLoader)

app = cdk.App()
env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION"))
stack = IDPBedrockStack(scope=app, stack_name=stack_config["stack_name"], config=stack_config, env=env)

NagSuppressions.add_stack_suppressions(
    stack,
    [
        {"id": "AwsSolutions-IAM4", "reason": "Using default AWS managed policy for CloudWatch logs for API Gateway"},
        {"id": "AwsSolutions-CFR4", "reason": "Using default CloudFront settings"},
        {"id": "AwsSolutions-CFR5", "reason": "Using default CloudFront settings"},
        {
            "id": "AwsSolutions-EC23",
            "reason": "False positive, all traffic is only allowed within the same security group",
        },
    ],
    True,
)

if stack_config["cdk_nag"]:
    cdk.Aspects.of(app).add(AwsSolutionsChecks())

app.synth()
