"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Utilities
"""

import json
import time
from typing import Any, Dict, Optional, Sequence, Union

import boto3

client = boto3.client("stepfunctions")


def run_idp_bedrock_api(
    state_machine_arn: str,
    documents: Union[str, Sequence[str]],
    attributes: Sequence[Dict[str, Any]],
    parsing_mode: Optional[str] = "Amazon Textract",
    instructions: Optional[str] = "",
    few_shots: Optional[Sequence[Dict[str, Any]]] = [],
    model_params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Run IDP Bedrock to extract custom attributes and scores from the text(s)

    Parameters
    ----------
    state_machine_arn: str
        ARN of the IDP Bedrock Step Function
    documents : Union[str, Sequence[str]]
        Either the document text or a list of document texts to run detection on
    attributes : Dict[str, Any]
        List of dictionaries for each entity and/or score to calculate based on the document text(s).
        Each dictionary must include the following keys:
            name : str
                Name of the entity (e.g., "person_name")
            description : str
                Description of the entity (e.g., "all names mentioned in the document")
            type : str
                Entity type. Must be one of: ["auto", "character", "number", "true/false"]
    parsing_mode : Optional[str]
        Parsing mode to use, either "Amazon Textract" or "Amazon Bedrock"
    instructions : Optional[str]
        Optional high-level instructions, by default ""
    few_shots: Optional[Sequence[Dict[str, Any]]]
        Optional list of few shots as dictionaries.
        Each dictionary contains
            input: str
                Input text of the example
            output: Any
                Output of the example should be a JSON formatted string
                The json should encode a dictionary
                The keys should be identical to the attributes you want to extract (e.g. "person_name")
                The values should be the values of the attributes you want to extract
    model_params : Optional[Dict[str, str]], optional
        LLM inference parameters, by default None

    Returns
    -------
    Dict[str, Any]
        Dictionary with values of the extracted attributes and scores
    """

    if model_params is None:
        model_params = {"model_id": "anthropic.claude-3-haiku-20240307-v1:0", "output_length": 2000, "temperature": 0.0}

    if isinstance(documents, str):
        documents = [documents]

    event = json.dumps(
        {
            "attributes": attributes,
            "documents": documents,
            "instructions": instructions,
            "few_shots": few_shots,
            "model_params": model_params,
            "parsing_mode": parsing_mode,
        }
    )

    response = client.start_execution(
        stateMachineArn=state_machine_arn,
        input=event,
    )

    execution_arn = response["executionArn"]

    while True:
        time.sleep(int(1))

        response = client.describe_execution(executionArn=execution_arn)
        status = response["status"]

        results = []

        if status == "FAILED":
            raise Exception("Step Function execution failed")

        if status == "SUCCEEDED":
            outputs = json.loads(response["output"])
            for output in outputs:
                results.append(
                    {"file_key": output["llm_answer"]["file_key"], "attributes": output["llm_answer"]["answer"]}
                )
            break

    return results
