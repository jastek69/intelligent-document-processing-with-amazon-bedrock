from typing import Any, Dict, List, Tuple

ALL_MODEL_SPECS = {
    "Claude 3.5 Sonnet (new)": {
        "MODEL_ID": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Claude 3.5 Sonnet": {
        "MODEL_ID": "anthropic.claude-3-5-sonnet-20240620-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Claude 3 Opus": {
        "MODEL_ID": "anthropic.claude-3-opus-20240229-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Claude 3 Sonnet": {
        "MODEL_ID": "anthropic.claude-3-sonnet-20240229-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Claude 3 Haiku": {
        "MODEL_ID": "anthropic.claude-3-haiku-20240307-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Claude 2.1": {
        "MODEL_ID": "anthropic.claude-v2:1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Claude 2": {
        "MODEL_ID": "anthropic.claude-v2",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Claude Instant": {
        "MODEL_ID": "anthropic.claude-instant-v1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Mistral Large": {
        "MODEL_ID": "mistral.mistral-large-2402-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Mistral Small": {
        "MODEL_ID": "mistral.mistral-small-2402-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Mixtral 8X7B": {
        "MODEL_ID": "mistral.mixtral-8x7b-instruct-v0:1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Mistral 7B": {
        "MODEL_ID": "mistral.mistral-7b-instruct-v0:2",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Titan Premier": {
        "MODEL_ID": "amazon.titan-text-premier-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Titan Express": {
        "MODEL_ID": "amazon.titan-text-express-v1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Titan Lite": {
        "MODEL_ID": "amazon.titan-text-lite-v1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Llama 3 70B": {
        "MODEL_ID": "meta.llama3-70b-instruct-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Llama 3 8B": {
        "MODEL_ID": "meta.llama3-8b-instruct-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Llama 2 70B": {
        "MODEL_ID": "meta.llama2-70b-chat-v1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Llama 2 13B": {
        "MODEL_ID": "meta.llama2-13b-chat-v1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Cohere Command R+": {
        "MODEL_ID": "cohere.command-r-plus-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Cohere Command R": {
        "MODEL_ID": "cohere.command-r-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Cohere Command": {
        "MODEL_ID": "cohere.command-text-v14",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Cohere Command Light": {
        "MODEL_ID": "cohere.command-light-text-v14",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Jamba-Instruct": {
        "MODEL_ID": "ai21.jamba-instruct-v1:0",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Jurassic 2 Ultra": {
        "MODEL_ID": "ai21.j2-ultra-v1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
    "Jurassic 2 Mid": {
        "MODEL_ID": "ai21.j2-mid-v1",
        "TEMPERATURE_DEFAULT": 0.0,
    },
}


def get_models_specs(bedrock_model_ids: List) -> Tuple[List[str], Dict[str, Any]]:
    """
    Get list of models displayed in the UI and their specs (i.e. their default parameters)
    """
    model_specs = {key: value for key, value in ALL_MODEL_SPECS.items() if value["MODEL_ID"] in bedrock_model_ids}

    models_displayed = list(model_specs.keys())

    return models_displayed, model_specs
