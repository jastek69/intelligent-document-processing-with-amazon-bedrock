import os

import boto3

ssm_client = boto3.client("ssm")


def load_ssm_params(path_prefix: str, next_tkn: str = ""):
    """Recursive function that loads SSM Parameters and set OS environment variables"""
    response = ssm_client.get_parameters_by_path(Path=path_prefix, NextToken=next_tkn)
    for param in response["Parameters"]:
        os.environ[param["Name"].split(path_prefix)[1]] = param["Value"]
    if response.get("NextToken", None):
        load_ssm_params(path_prefix, next_tkn=response["NextToken"])
