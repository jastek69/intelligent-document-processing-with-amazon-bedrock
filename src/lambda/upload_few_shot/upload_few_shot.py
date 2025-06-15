"""
Copyright © Amazon.com and Affiliates
"""

import logging
import os
import sys
import json
import boto3
import datetime

DYNAMODB = boto3.resource("dynamodb")
FEW_SHOTS_TABLE_NAME = os.environ["FEW_SHOTS_TABLE_NAME"]

LOGGER = logging.Logger("Create-Dynamo-Entry", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


def create_dynamo_entry(table_name, example_name, s3_file_location, s3_marking_location):
    table = DYNAMODB.Table(table_name)
    # add date + time to example name
    example_id = example_name + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    table.put_item(
        Item={"ExampleId": example_id, "file_location": s3_file_location, "marking_location": s3_marking_location}
    )
    return example_id


def lambda_handler(event, context):
    """
    Lambda handler
    """
    LOGGER.info("Starting execution of lambda_handler()")
    event = json.loads(event["body"])
    # get s3_file_location and s3_marking_location from event
    s3_file_location = event["s3_file_location"]
    s3_marking_location = event["s3_marking_location"]
    example_name = event["example_name"]
    example_id = create_dynamo_entry(FEW_SHOTS_TABLE_NAME, example_name, s3_file_location, s3_marking_location)
    LOGGER.info(f"Added example to the {FEW_SHOTS_TABLE_NAME} table.")
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"example_id": example_id}),
    }
