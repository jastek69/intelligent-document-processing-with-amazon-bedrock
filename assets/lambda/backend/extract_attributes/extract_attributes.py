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
from langchain import LLMChain
from langchain_aws import ChatBedrock
from model.bedrock import create_bedrock_client, get_model_params
from model.parser import parse_json_string
from prompt import load_prompt_template
from utils import filled_prompt, token_count_tokenizer, truncate_document

LOGGER = logging.Logger("ENTITY-EXTRACTION", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


#########################
#       CONSTANTS
#########################

MAX_DOC_LENGTH_DIC = {
    "anthropic.claude-3-5-haiku-20241022-v1:0": 200_000,
    "anthropic.claude-3-5-sonnet-20241022-v2:0": 200_000,
    "anthropic.claude-3-5-sonnet-20240620-v1:0": 200_000,
    "anthropic.claude-3-opus-20240229-v1:0": 200_000,
    "anthropic.claude-3-sonnet-20240229-v1:0": 200_000,
    "anthropic.claude-3-haiku-20240307-v1:0": 200_000,
    "anthropic.claude-v2:1": 200_000,
    "anthropic.claude-v2": 100_000,
    "anthropic.claude-instant-v1": 100_000,
    "mistral.mistral-large-2402-v1:0": 32_000,
    "mistral.mistral-small-2402-v1:0": 32_000,
    "mistral.mixtral-8x7b-instruct-v0:1": 32_000,
    "mistral.mistral-7b-instruct-v0:2": 32_000,
    "amazon.titan-text-premier-v1:0": 32_000,
    "amazon.titan-text-express-v1": 8_000,
    "amazon.titan-text-lite-v1": 4_000,
    "meta.llama3-70b-instruct-v1:0": 8_000,
    "meta.llama3-8b-instruct-v1:0": 8_000,
    "meta.llama2-70b-chat-v1": 4_096,
    "meta.llama2-13b-chat-v1": 4_096,
    "cohere.command-r-plus-v1:0": 128_000,
    "cohere.command-r-v1:0": 128_000,
    "cohere.command-text-v14": 4_000,
    "cohere.command-light-text-v14": 4_000,
    "ai21.jamba-instruct-v1:0": 256_000,
    "ai21.j2-ultra-v1": 8_191,
    "ai21.j2-mid-v1,": 8_191,
}

GENERATOR_CONFIG = {
    "top_p": 1,  # cumulative probability of sampled tokens
    "top_k": 50,  # number of the top most probable tokens to sample
    "stop_words": [],  # words after which the generation is stopped
    "max_tokens": 4_096,  # max tokens to be generated
}

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
    GENERATOR_CONFIG["temperature"] = body["model_params"]["temperature"]
    model_id = body["model_params"]["model_id"]

    if model_id.split(".")[0] == "meta":
        GENERATOR_CONFIG["max_tokens"] = 2048

    model_params = get_model_params(model_id=model_id, params=GENERATOR_CONFIG)
    LOGGER.info(f"LLM parameters: {model_id}; {model_params}")

    # extract document and attributes
    document = body["document"]

    attributes = body["attributes"]
    instructions = body.get("instructions", "")
    few_shots = body.get("few_shots", [])
    LOGGER.info(f"few_shots : {few_shots}")
    attributes_str = ""
    for i in range(len(attributes)):
        attributes_str += f"{i+1}. {attributes[i]['name']}: {attributes[i]['description']}"
        if "type" in attributes[i] and attributes[i]["type"].lower() != "auto":
            attributes_str += f" (must be {attributes[i]['type'].lower()})."
        attributes_str += "\n"

    # set up LLM
    llm = ChatBedrock(
        client=BEDROCK_CLIENT,
        model_id=model_id,
        model_kwargs=model_params,
    )

    # prepare prompt template
    prompt_template = load_prompt_template(num_few_shots=len(few_shots), instructions=instructions)
    LOGGER.info(f"Prompt template: {prompt_template}")

    filled_template = filled_prompt(
        few_shots=few_shots,
        attributes=attributes,
        instructions=instructions,
        template=prompt_template.template,
        document=document,
    )

    # count total tokens in filled prompt and document
    token_count_doc = token_count_tokenizer(document, model=model_id)
    token_count_total = token_count_tokenizer(filled_template, model=model_id)
    LOGGER.info(f"Filled prompt template + document token count: {token_count_total}")

    document = truncate_document(
        document=document,
        token_count_total=token_count_total,
        model=model_id,
        num_token_prompt=token_count_total - token_count_doc,
        max_token_model=MAX_DOC_LENGTH_DIC[model_id] * 0.75,
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

    # run entity extraction
    LOGGER.info(f"Calling the LLM {model_id} to extract attributes...")
    llm_chain = LLMChain(llm=llm, prompt=prompt_template, verbose=False)
    response = llm_chain.invoke(prompt_variables)
    LOGGER.info(f"LLM response: {response['text']}")

    # parse response
    try:
        response_json = parse_json_string(response["text"])
    except Exception as e:
        LOGGER.debug(f"Error parsing response: {e}")
        response_json = {}
    LOGGER.info(f"Parsed response: {response_json}")

    json_data = json.dumps(
        {
            "answer": response_json,
            "raw_answer": response["text"],
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
