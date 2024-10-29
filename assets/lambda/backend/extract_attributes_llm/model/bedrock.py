"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Utils for Bedrock
"""

import boto3


def create_bedrock_client(bedrock_region, bedrock_config=None):
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=bedrock_region,
        config=bedrock_config,
    )


def get_model_params(
    model_id: str,
    params: dict,
) -> dict:
    """
    Set up a dictionary with model parameters named appropriately for Bedrock

    Parameters
    ----------
    model_id : str
        LLM model ID
    params : dict
        Model-specific inference parameters

    Returns
    -------
    dict
        Bedrock-aligned inference parameters
    """

    model_params = {}

    if model_id.startswith("ai21"):
        model_params = {
            "maxTokens": params["max_tokens"],
            "stopSequences": params["stop_words"],
            "temperature": params["temperature"],
            "topP": params["top_p"],
            "topKReturn": params["top_k"],
        }
    elif model_id.startswith("amazon"):
        model_params = {
            "maxTokenCount": params["max_tokens"],
            "stopSequences": [],
            "temperature": params["temperature"],
            "topP": params["top_p"],
        }
    elif model_id.startswith("anthropic"):
        model_params = {
            "max_tokens": params["max_tokens"],
            "stop_sequences": params["stop_words"],
            "temperature": params["temperature"],
            "top_p": params["top_p"],
            "top_k": params["top_k"],
        }
    elif model_id.startswith("cohere"):
        model_params = {
            "max_tokens": params["max_tokens"],
            "temperature": params["temperature"],
            "p": params["top_p"],
            "k": params["top_k"],
        }
    elif model_id.startswith("meta"):
        model_params = {
            "max_gen_len": params["max_tokens"],
            "temperature": params["temperature"],
            "top_p": params["top_p"],
        }
    elif model_id.startswith("mistral"):
        model_params = {
            "max_tokens": params["max_tokens"],
            "temperature": params["temperature"],
            "top_p": params["top_p"],
            "top_k": params["top_k"],
        }

    return model_params
