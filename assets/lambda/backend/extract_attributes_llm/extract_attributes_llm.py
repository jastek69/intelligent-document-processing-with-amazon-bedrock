"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
IDP with Vision LLM
"""

#########################
#   LIBRARIES & LOGGER
#########################

import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import boto3
from model.bedrock import call_bedrock
from botocore.config import Config
from helpers import (
    create_assistant_response,
    create_human_message_with_imgs,
    create_human_message_with_imgs_generator,
    combine_json_responses,
)
from model.bedrock import create_bedrock_client, get_model_params
from model.parser import parse_json_string
from prompt import SYSTEM_PROMPT, load_prompt_template
from utils import filled_prompt  # token_count_tokenizer, truncate_document

LOGGER = logging.Logger("IDP-MULTIMODAL", level=logging.DEBUG)
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


#########################
#        HELPERS
#########################


def get_marked_example(prompt: str, few_shot_example: dict) -> list[dict]:
    """
    Get marked example for few-shot learning by downloading files from S3.
    """
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


def parse_event(event: dict) -> dict:
    """
    Parse the incoming event and extract the body.
    """
    if "requestContext" in event:
        LOGGER.info("Received HTTP request.")
        return json.loads(event["body"])
    # step functions invocation
    return event["body"]


def download_file_from_s3(file_key: str, s3_client: boto3.client, bucket: str) -> str | None:
    """
    Download a file from S3 to local lambda storage.
    """
    if not file_key:
        return None

    ending = file_key.split(".")[-1]
    local_path = f"/tmp/file.{ending}"
    s3_client.download_file(bucket, file_key, local_path)
    LOGGER.info(f"Downloaded file to {local_path}")
    return local_path


def process_chunk(
    index: int,
    chunk_messages: list[dict],
    model_id: str,
    system_prompt: str,
    temperature: float,
    bedrock_client: boto3.client,
    logger: logging.Logger,
) -> tuple[dict, str]:
    """
    Process a single chunk of messages.
    """
    logger.info(f"Processing chunk {index + 1} with {len(chunk_messages[-1]['content']) - 1} images...")

    # Call Bedrock for this chunk using the call_bedrock function
    response_text, _ = call_bedrock(
        messages=chunk_messages,
        model_id=model_id,
        system_prompt=system_prompt,
        temperature=temperature,
        bedrock_client=bedrock_client,
        logger=logger,
    )

    logger.info(f"Received LLM response for chunk {index + 1}")

    try:
        response_json = parse_json_string(response_text)
        logger.info(f"Chunk {index + 1} parsed JSON: {response_json}")
        return response_json, response_text
    except Exception as e:
        logger.debug(f"Error parsing response for chunk {index + 1}: {e}")
        # Return empty dict so we maintain chunk count
        return {}, response_text


def process_chunks(
    chunk_messages_list: list[list[dict]],
    model_id: str,
    system_prompt: str,
    temperature: float,
    bedrock_client: boto3.client,
    parallel_processing: bool,
    logger: logging.Logger,
):
    """
    Process all chunks either in parallel or sequentially.
    """
    all_responses = []
    all_raw_responses = []

    if parallel_processing and len(chunk_messages_list) > 1:
        logger.info(f"Processing {len(chunk_messages_list)} chunks in parallel")
        with ThreadPoolExecutor(max_workers=min(10, len(chunk_messages_list))) as executor:
            # Create a future for each chunk
            futures = [
                executor.submit(
                    process_chunk,
                    index=i,
                    chunk_messages=chunk_msgs,
                    model_id=model_id,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    bedrock_client=bedrock_client,
                    logger=logger,
                )
                for i, chunk_msgs in enumerate(chunk_messages_list)
            ]

            # Collect results as they complete
            for i, future in enumerate(futures):
                try:
                    response_json, response_text = future.result()
                    all_responses.append(response_json)
                    all_raw_responses.append(response_text)
                    logger.info(
                        f"Successfully processed chunk {i + 1}: response type={type(response_json).__name__},\
                            keys={list(response_json.keys()) if isinstance(response_json, dict) else 'N/A'}"
                    )
                except Exception as e:
                    logger.error(f"Error processing chunk {i + 1}: {str(e)}")
                    all_responses.append({})
                    all_raw_responses.append(f"Error: {str(e)}")
    else:
        # Process sequentially
        logger.info(f"Processing {len(chunk_messages_list)} chunks sequentially")
        for i, chunk_msgs in enumerate(chunk_messages_list):
            response_json, response_text = process_chunk(
                index=i,
                chunk_messages=chunk_msgs,
                model_id=model_id,
                system_prompt=system_prompt,
                temperature=temperature,
                bedrock_client=bedrock_client,
                logger=logger,
            )
            all_responses.append(response_json)
            all_raw_responses.append(response_text)
            logger.info(
                f"Sequential processing - chunk {i + 1}: response type={type(response_json).__name__},\
                    keys={list(response_json.keys()) if isinstance(response_json, dict) else 'N/A'}"
            )

    return all_responses, all_raw_responses


def prepare_and_store_response(
    all_responses: list[dict],
    all_raw_responses: list[str],
    file_name: str,
    s3_client: boto3.client,
    bucket: str,
    prefix: str,
) -> str:
    """
    Combine responses and store the result in S3.
    """
    # Log individual responses before combining
    for i, response in enumerate(all_responses):
        LOGGER.info(f"Response {i + 1} before combining: type={type(response).__name__}, content={response}")

    # If we processed multiple chunks, combine the responses
    if len(all_responses) > 1:
        LOGGER.info(f"Combining responses from {len(all_responses)} chunks...")
        combined_response = combine_json_responses(all_responses)
        # Join raw responses with clear demarcation
        raw_response = "\n\n".join([f"CHUNK {i + 1}:\n{resp}" for i, resp in enumerate(all_raw_responses)])
    else:
        # If only one chunk was processed, use the single response
        combined_response = all_responses[0] if all_responses else {}
        raw_response = all_raw_responses[0] if all_raw_responses else ""

    LOGGER.info(f"Final combined response: {combined_response}")
    LOGGER.info(f"Final combined response type: {type(combined_response).__name__}")

    json_data = json.dumps(
        {
            "answer": combined_response,
            "raw_answer": raw_response,
            "file_key": file_name,
            "original_file_name": file_name,
            "chunks_processed": len(all_responses),
        }
    )

    s3_client.put_object(
        Body=json_data,
        Bucket=bucket,
        Key=f"{prefix}/{file_name.split('/', 1)[-1].removesuffix('.txt')}.json",
        ContentType="application/json",
    )

    return json_data


#########################
#        HANDLER
#########################


def lambda_handler(event, context):
    """
    Lambda handler for extracting attributes from documents using LLM.
    """
    LOGGER.debug(f"event: {event}")

    # Parse event
    body = parse_event(event)
    LOGGER.info(f"Received input: {body}")

    # Extract parameters
    file_key = body.get("file_name")
    attributes = body["attributes"]
    instructions = body.get("instructions", "")
    few_shots = body.get("few_shots", {})
    chunk_size = body.get("chunk_size", 10)
    parallel_processing = body.get("parallel_processing", True)

    if few_shots:
        LOGGER.info(f"Few shot examples provided: {few_shots}")

    # Get model ID and params
    model_params = get_model_params()
    model_params["temperature"] = body["model_params"]["temperature"]
    model_id = body["model_params"]["model_id"]
    LOGGER.info(f"LLM parameters: {model_id}; {model_params}")

    # Prepare prompt template
    prompt_template, _ = load_prompt_template(instructions=instructions)
    LOGGER.info(f"Prompt template: {prompt_template}")
    filled_template = filled_prompt(
        attributes=attributes,
        instructions=instructions,
        template=prompt_template,
    )
    messages = []
    LOGGER.info("Using Bedrock LLM")

    # Download file if provided
    file = download_file_from_s3(file_key, S3_CLIENT, S3_BUCKET)

    # Add few-shot examples if provided
    if few_shots:
        LOGGER.info(f"Adding few-shot example with the name {few_shots}")
        example_messages = get_marked_example(filled_template, few_shots)
        messages.extend(example_messages)

    LOGGER.info(f"Processing with chunk_size={chunk_size}, parallel_processing={parallel_processing}")

    # Create a generator that yields messages with chunked images
    message_generator = create_human_message_with_imgs_generator(filled_template, file, max_pages=chunk_size)

    # Collect all messages first so we can process them in parallel if requested
    chunk_messages_list = []
    for human_message in message_generator:
        chunk_messages = messages.copy()  # Start with base messages (including few-shots if any)
        chunk_messages.append(human_message)
        chunk_messages_list.append(chunk_messages)
    LOGGER.info(f"Prepared {len(chunk_messages_list)} chunks for processing")

    # Process all chunks
    all_responses, all_raw_responses = process_chunks(
        chunk_messages_list=chunk_messages_list,
        model_id=model_id,
        system_prompt=SYSTEM_PROMPT,
        temperature=model_params["temperature"],
        bedrock_client=BEDROCK_CLIENT,
        parallel_processing=parallel_processing,
        logger=LOGGER,
    )

    # Prepare and store the response
    json_data = prepare_and_store_response(
        all_responses=all_responses,
        all_raw_responses=all_raw_responses,
        file_name=body["file_name"],
        s3_client=S3_CLIENT,
        bucket=S3_BUCKET,
        prefix=PREFIX_ATTRIBUTES,
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json_data,
    }
