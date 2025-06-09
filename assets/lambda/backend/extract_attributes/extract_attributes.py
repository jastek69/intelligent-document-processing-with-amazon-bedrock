"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Lambda for extracting features from texts
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
from model.bedrock import create_bedrock_client, get_model_params
from model.parser import parse_json_string, parse_bedrock_response
from prompt import load_prompt_template
from utils import filled_prompt, token_count_tokenizer, truncate_document, get_max_input_token

LOGGER = logging.Logger("IDP", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


#########################
#       CONSTANTS
#########################

BEDROCK_REGION = os.environ["BEDROCK_REGION"]
BEDROCK_CONFIG = Config(connect_timeout=120, read_timeout=120, retries={"max_attempts": 5})
BEDROCK_CLIENT = create_bedrock_client(BEDROCK_REGION, BEDROCK_CONFIG)

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

    # load document text
    if "document" not in body:
        s3 = boto3.resource("s3")
        content_object = s3.Object(S3_BUCKET, body["file_key"])
        body["document"] = content_object.get()["Body"].read().decode("utf-8")
    LOGGER.info(f"Loaded text with {len(body['document'])} chars: {body['document'][:100]}...")

    # get model ID and params
    model_params = get_model_params()
    model_params["temperature"] = body["model_params"]["temperature"]
    model_id = body["model_params"]["model_id"]
    LOGGER.info(f"LLM parameters: {model_id}; {model_params}")

    # extract document and attributes
    document = body["document"]
    attributes = body["attributes"]
    instructions = body.get("instructions", "")
    few_shots = body.get("few_shots", [])
    LOGGER.info(f"few_shots : {few_shots}")
    attributes_str = ""
    for i in range(len(attributes)):
        attributes_str += f"{i + 1}. {attributes[i]['name']}: {attributes[i]['description']}"
        if "type" in attributes[i] and attributes[i]["type"].lower() != "auto":
            attributes_str += f" (must be {attributes[i]['type'].lower()})."
        attributes_str += "\n"

    # prepare prompt template
    prompt_template, _ = load_prompt_template(num_few_shots=len(few_shots), instructions=instructions)
    LOGGER.info(f"Prompt template: {prompt_template}")
    filled_template = filled_prompt(
        few_shots=few_shots,
        attributes=attributes,
        instructions=instructions,
        template=prompt_template,
        document=document,
    )

    # count total tokens in filled prompt and document
    token_count_doc = token_count_tokenizer(document, model=model_id)
    token_count_total = token_count_tokenizer(filled_template, model=model_id)
    max_token_model = get_max_input_token(model_id)
    LOGGER.info(f"Filled prompt template + document token count: {token_count_total}")

    document = truncate_document(
        document=document,
        token_count_total=token_count_total,
        model=model_id,
        num_token_prompt=token_count_total - token_count_doc,
        max_token_model=max_token_model * 0.75,
    )
    prompt_variables = {
        "document": document,
        "attributes": attributes_str,
    }
    if instructions.strip():
        prompt_variables["instructions"] = instructions
    for i, shot in enumerate(few_shots):
        prompt_variables.update(
            {
                f"few_shot_input_{i}": json.dumps(shot["input"], indent=4),
                f"few_shot_output_{i}": json.dumps(shot["output"], indent=4),
            }
        )
        LOGGER.info(f"Few shot {i}: {shot}")

    # build messages list
    for variable in prompt_variables:
        prompt_template = prompt_template.replace(f"{{{variable}}}", prompt_variables[variable])
    messages = [{"role": "user", "content": [{"text": prompt_template}]}]

    # invoke LLM
    LOGGER.info(f"Invoking {model_id}...")
    bedrock_response = BEDROCK_CLIENT.converse(
        modelId=model_id,
        inferenceConfig=model_params,
        messages=messages,
    )
    response = parse_bedrock_response(bedrock_response)
    LOGGER.info(f"LLM response: {response}")

    # parse response
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
            "file_key": body["file_key"],
            "original_file_name": body["original_file_name"],
        }
    )

    S3_CLIENT.put_object(
        Body=json_data,
        Bucket=S3_BUCKET,
        Key=f"{PREFIX_ATTRIBUTES}/{body['file_key'].split('/', 1)[-1].removesuffix('.txt')}.json",
        ContentType="application/json",
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json_data,
    }
