import logging
import os
import sys
import json
import boto3

DYNAMODB = boto3.resource("dynamodb")
FEW_SHOTS_TABLE_NAME = os.environ["FEW_SHOTS_TABLE_NAME"]

LOGGER = logging.Logger("Load-Few-Shots-List", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter(
"%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


def retrieve_customer_list(table_name):
    table = DYNAMODB.Table(table_name)
    response = table.scan()
    if response["Items"]:
        LOGGER.info(f"Loaded {len(response['Items'])} examples")
        return [x["ExampleId"] for x in response["Items"]]
    return None


def lambda_handler(event, context):
    """
    Lambda handler
    """
    LOGGER.info("Starting execution of lambda_handler()")
    event = json.loads(event["body"])
    examples_list = retrieve_customer_list(FEW_SHOTS_TABLE_NAME)
    LOGGER.info(f"Loaded customers list: {examples_list}")
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"examples_list": examples_list}),
    }
