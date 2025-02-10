"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------

"""

#########################
#   LIBRARIES & LOGGER
#########################

import json
import logging
import os
import sys

import boto3
from botocore.config import Config
from helpers import create_assistant_response, create_human_message_with_imgs
from model.bedrock import create_bedrock_client, get_model_params
from model.parser import parse_json_string, parse_bedrock_response
from prompt import SYSTEM_PROMPT, load_prompt_template
from utils import filled_prompt  # token_count_tokenizer, truncate_document

LOGGER = logging.Logger("ENTITY-EXTRACTION-MULTIMODAL", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


#########################
#       CONSTANTS
#########################

BEDROCK_REGION = os.environ["BEDROCK_REGION"]
BEDROCK_CONFIG = Config(connect_timeout=120, read_timeout=120, retries={"max_attempts": 5})
BEDROCK_CLIENT = create_bedrock_client(BEDROCK_REGION, BEDROCK_CONFIG)
DYNAMODB = boto3.resource("dynamodb")

S3_BUCKET = os.environ["BUCKET_NAME"]
S3_CLIENT = boto3.client("s3")

FEW_SHOTS_TABLE_NAME = os.environ["FEW_SHOTS_TABLE_NAME"]

PREFIX_ATTRIBUTES = "attributes"
MARKINGS_FOLDER = "markings"


def get_marked_example(prompt, few_shot_example):
    LOGGER.info("Adding few shot examples")

    pdf_file_key_s3 = few_shot_example["documents"][0]
    marking_file_key_s3 = few_shot_example["markings"]

    os.makedirs(f"/tmp/fewshots/{MARKINGS_FOLDER}", exist_ok=True)
    file_path = f"/tmp/fewshots/{pdf_file_key_s3.split('/')[-1]}"
    marking_file_path = f"/tmp/fewshots/{marking_file_key_s3.split('/')[-1]}"

    S3_CLIENT.download_file(S3_BUCKET, pdf_file_key_s3, file_path)
    S3_CLIENT.download_file(S3_BUCKET, marking_file_key_s3, marking_file_path)

    LOGGER.info(f"Downloaded marked example from s3://{S3_BUCKET}/{pdf_file_key_s3}")

    return [create_human_message_with_imgs(prompt, file_path), create_assistant_response(marking_file_path, file_path)]


def lambda_handler(event, context):
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

    file_key = body.get("file_name")
    attributes = body["attributes"]
    instructions = body.get("instructions", "")
    few_shots = body.get("few_shots", {})

    if few_shots:
        LOGGER.info(f"Few shot examples provided: {few_shots}")

    # get model ID and params
    model_params = get_model_params()
    model_params["temperature"] = body["model_params"]["temperature"]
    model_id = body["model_params"]["model_id"]
    LOGGER.info(f"LLM parameters: {model_id}; {model_params}")

    # prepare prompt template
    prompt_template, _ = load_prompt_template(instructions=instructions)
    LOGGER.info(f"Prompt template: {prompt_template}")

    filled_template = filled_prompt(
        attributes=attributes,
        instructions=instructions,
        template=prompt_template,
    )

    messages = []

    LOGGER.info("Using Bedrock LLM.")

    # load file to local lambda storage if s3_location is given:
    if file_key:
        file_key_s3 = file_key
        ending = file_key_s3.split(".")[-1]
        S3_CLIENT.download_file(S3_BUCKET, file_key_s3, f"/tmp/file.{ending}")
        file = f"/tmp/file.{ending}"
        LOGGER.info(f"Downloaded file to /tmp/file.{ending}")

    # ============= FEW SHOTS LOGIC: yet to be added ============
    if few_shots:
        LOGGER.info(f"Adding few-shot example with the name {few_shots}")
        # get a pair of messages: user message - assistant response
        example_messages = get_marked_example(filled_template, few_shots)
        messages.extend(example_messages)

    # read example
    human_message = create_human_message_with_imgs(filled_template, file, max_pages=20)
    messages.append(human_message)
    LOGGER.info(f"Calling the LLM {model_id} to extract attributes...")
    # for debugging purposes
    # LOGGER.info(f"Messages: {messages}")
    bedrock_response = BEDROCK_CLIENT.converse(
        modelId=model_id,
        inferenceConfig=model_params,
        messages=messages,
        system=[{"text": SYSTEM_PROMPT}],
    )
    response = parse_bedrock_response(bedrock_response)
    LOGGER.info(f"LLM response: {response}")

    try:
        response_json = parse_json_string(response)
    except Exception as e:
        LOGGER.debug(f"Error parsing response: {e}")
        response_json = {}
    LOGGER.info(f"Parsed response: {response_json}")

    json_data = json.dumps(
        {
            "answer": response_json,
            "raw_answer": response,
            "file_key": body["file_name"],
            "original_file_name": body["file_name"],
        }
    )

    S3_CLIENT.put_object(
        Body=json_data,
        Bucket=S3_BUCKET,
        Key=f"{PREFIX_ATTRIBUTES}/{body['file_name'].split('/', 1)[-1].removesuffix('.txt')}.json",
        ContentType="application/json",
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json_data,
    }
