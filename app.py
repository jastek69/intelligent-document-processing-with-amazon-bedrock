"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
Package content:
    Entry point of the CDK application
"""

import os
from pathlib import Path
import logging
import sys
import aws_cdk as cdk
import yaml
from cdk_nag import AwsSolutionsChecks, NagSuppressions
from yaml.loader import SafeLoader

from infra.stack import IDPBedrockStack

LOGGER = logging.Logger("APP-BUILD", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)
LOGGER.addHandler(HANDLER)

ROOT = Path(__file__).parent
if "config.yml" in os.listdir(ROOT):
    LOGGER.info("Found config.yml file in root directory.")
    STACK_CONFIG_PATH = os.path.join(ROOT, "config.yml")
elif "config-example.yml" in os.listdir(ROOT):
    LOGGER.warning("Did not find config.yml but using config-example.yml from the root directory.")
    STACK_CONFIG_PATH = os.path.join(ROOT, "config-example.yml")
else:
    raise RuntimeError("Cannot find config file in root directory.")

with open(STACK_CONFIG_PATH, "r", encoding="utf-8") as yaml_file:
    stack_config = yaml.load(yaml_file, Loader=SafeLoader)

LOGGER.info("Creating app scope")
app = cdk.App()
env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=stack_config["stack_region"])
LOGGER.info(f"Creating solution stack using {env=} and {stack_config=}")
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
        {
            "id": "AwsSolutions-IAM5",
            "reason": "CognitoUpdaterRole needs wildcard log access for its Lambda function.",
        },
    ],
    True,
)

if stack_config["cdk_nag"]:
    LOGGER.info("Running cdk-nag")
    cdk.Aspects.of(app).add(AwsSolutionsChecks())

LOGGER.info("Synthesizing app")
app.synth()
LOGGER.info("Done!")
