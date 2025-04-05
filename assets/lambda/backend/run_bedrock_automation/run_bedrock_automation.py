"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Lambda for extracting features from documents
"""

#########################
#   LIBRARIES & LOGGER
#########################

import json
import logging
import os
import sys
import time
import boto3
from botocore.config import Config

LOGGER = logging.Logger("BEDROCK-AUTOMATION", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


#########################
#       CONSTANTS
#########################

BEDROCK_REGION = os.environ["BEDROCK_REGION"]
BEDROCK_CONFIG = Config(connect_timeout=120, read_timeout=120, retries={"max_attempts": 5})

BDA_CLIENT = boto3.client("bedrock-data-automation", region_name=BEDROCK_REGION, config=BEDROCK_CONFIG)
BDA_RUNTIME_CLIENT = boto3.client("bedrock-data-automation-runtime", region_name=BEDROCK_REGION, config=BEDROCK_CONFIG)

S3_BUCKET = os.environ["BUCKET_NAME"]
S3_CLIENT = boto3.client("s3")

PREFIX_ATTRIBUTES = "attributes"


#########################
#        HANDLER
#########################


def lambda_handler(event, context):  # noqa: C901
    """
    Lambda handler
    """

    LOGGER.debug(f"event: {event}")

    # parse event
    if "requestContext" in event:
        LOGGER.info("Received HTTP request.")
        body = json.loads(event["body"])
    else:  # step functions invocation
        body = event["body"]
    LOGGER.info(f"Received input: {body}")

    # get file S3 path
    file_name = body["file_name"]
    file_source = f"s3://{S3_BUCKET}/{file_name}"

    # format attributes
    attributes = body["attributes"]
    formatted_attributes = {
        item["name"]: {"type": "string", "inferenceType": "inferred", "instruction": item["description"]}
        for item in attributes
    }

    # define blueprint
    timestamp = time.strftime("%Y-%m-%d-%H-%M-%S")
    blueprint_name = f"idp-blueprint-{hash(json.dumps(formatted_attributes))}"
    blueprint_description = f"idp-blueprint-last-updated-{timestamp}"
    blueprint_type = "DOCUMENT"
    blueprint_stage = "LIVE"
    blueprint_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "description": blueprint_description,
        "class": "custom-document-class",
        "type": "object",
        "definitions": {},
        "properties": formatted_attributes,
    }

    # create or update blueprint
    list_blueprints_response = BDA_CLIENT.list_blueprints(blueprintStageFilter="ALL")
    blueprint = next(
        (
            blueprint
            for blueprint in list_blueprints_response["blueprints"]
            if "blueprintName" in blueprint and blueprint["blueprintName"] == blueprint_name
        ),
        None,
    )
    if not blueprint:
        response = BDA_CLIENT.create_blueprint(
            blueprintName=blueprint_name,
            type=blueprint_type,
            blueprintStage=blueprint_stage,
            schema=json.dumps(blueprint_schema),
        )
        LOGGER.info(f"Creating new blueprint with name={blueprint_name}, updating Stage and Schema")
    else:
        response = BDA_CLIENT.update_blueprint(
            blueprintArn=blueprint["blueprintArn"],
            blueprintStage=blueprint_stage,
            schema=json.dumps(blueprint_schema),
        )
        LOGGER.info(f"Found existing blueprint with name={blueprint_name}, updating Stage and Schema")
    blueprint_arn = response["blueprint"]["blueprintArn"]

    # start data invocation sync
    response = BDA_RUNTIME_CLIENT.invoke_data_automation_async(
        inputConfiguration={"s3Uri": file_source},
        outputConfiguration={"s3Uri": f"s3://{S3_BUCKET}/bda-outputs"},
        blueprints=[{"blueprintArn": blueprint_arn}],
        dataAutomationProfileArn=f"arn:aws:bedrock:{BEDROCK_REGION}:{S3_BUCKET.rsplit('-', 1)[-1]}:data-automation-profile/us.data-automation-v1",  # noqa: E501
    )
    invocationArn = response["invocationArn"]
    LOGGER.info(f"Invoked data automation job with invocation arn {invocationArn}")

    # wait for completion
    status = "None"
    while status not in ["Success", "ServiceError", "ClientError"]:
        time.sleep(int(1))
        LOGGER.info("Waiting for data automation job to complete...")

        try:
            status_response = BDA_RUNTIME_CLIENT.get_data_automation_status(invocationArn=invocationArn)
            LOGGER.info(f"Data automation job status response: {status_response}")
        except Exception as e:
            LOGGER.error(f"Error getting data automation job status: {e}")
            raise

        status = status_response["status"]
        LOGGER.info(f"Data automation job status: {status}")
        if status in ["ServiceError", "ClientError"]:
            raise Exception(status_response.get("errorMessage", "Data automation job failed"))

    LOGGER.info(f"Data automation job completed with status: {status}")

    job_metadata_s3_location = status_response["outputConfiguration"]["s3Uri"]

    # get custom output path
    s3_uri_parts = job_metadata_s3_location.removeprefix("s3://").split("/", 1)
    response = S3_CLIENT.get_object(Bucket=s3_uri_parts[0], Key=s3_uri_parts[1])
    job_metadata = json.loads(response["Body"].read().decode("utf-8"))
    custom_output_path = job_metadata["output_metadata"][0]["segment_metadata"][0]["custom_output_path"]

    # get extracted attributes JSON
    s3_uri_parts = custom_output_path.removeprefix("s3://").split("/", 1)
    response = S3_CLIENT.get_object(Bucket=s3_uri_parts[0], Key=s3_uri_parts[1])
    custom_outputs_json = json.loads(response["Body"].read().decode("utf-8"))
    attributes = custom_outputs_json["inference_result"]
    escaped_attributes = json.dumps(attributes).replace('"', '&quot;')
    raw_answer = "<thinking>No explanation available when using Bedrock Data Automation./</thinking>"
    raw_answer += f"<json>{escaped_attributes}</json>"
    
    json_data = json.dumps(
        {
            "answer": attributes,
            "raw_answer": raw_answer,
            "file_key": body["file_name"],
            "original_file_name": body["file_name"],
        }
    )

    S3_CLIENT.put_object(
        Body=json_data,
        Bucket=S3_BUCKET,
        Key=f"{PREFIX_ATTRIBUTES}/{body["file_name"].split('/', 1)[-1].rsplit('.', 1)[-1]}.json",
        ContentType="application/json",
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json_data,
    }
