"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    ...
"""

from dataclasses import asdict, dataclass


@dataclass
class BedrockParams:
    max_tokens: int
    stop_sequences: list
    temperature: float
    top_p: float


class ModelSpecificParams:
    __titan_mapping__ = {
        "max_tokens": "maxTokenCount",
        "stop_sequences": "stopSequences",
        "temperature": "temperature",
        "top_p": "topP",
    }
    __anthropic_mapping__ = {
        "max_tokens": "max_tokens",
        "stop_sequences": "stop_sequences",
        "temperature": "temperature",
        "top_p": "top_p",
    }
    __mistral_mapping__ = {
        "max_tokens": "max_tokens",
        "temperature": "temperature",
        "top_p": "top_p",
    }
    __cohere_mapping__ = {
        "max_tokens": "max_tokens",
        "temperature": "temperature",
    }
    __meta_mapping__ = {
        "max_tokens": "max_gen_len",
        "temperature": "temperature",
        "top_p": "top_p",
    }
    __ai21_mapping__ = {
        "max_tokens": "maxTokens",
        "stop_sequences": "stopSequences",
        "temperature": "temperature",
        "top_p": "topP",
    }
    __maps__ = {
        "anthropic.claude-3-5-haiku-20241022-v1:0": __anthropic_mapping__,
        "anthropic.claude-3-5-sonnet-20241022-v2:0": __anthropic_mapping__,
        "anthropic.claude-3-5-sonnet-20240620-v1:0": __anthropic_mapping__,
        "anthropic.claude-3-sonnet-20240229-v1:0": __anthropic_mapping__,
        "anthropic.claude-3-haiku-20240307-v1:0": __anthropic_mapping__,
        "anthropic.claude-v2:1": __anthropic_mapping__,
        "anthropic.claude-v2": __anthropic_mapping__,
        "anthropic.claude-v1": __anthropic_mapping__,
        "anthropic.claude-instant-v1": __anthropic_mapping__,
        "mistral.mistral-large-2402-v1:0": __mistral_mapping__,
        "mistral.mistral-small-2402-v1:0": __mistral_mapping__,
        "mistral.mixtral-8x7b-instruct-v0:1": __mistral_mapping__,
        "mistral.mistral-7b-instruct-v0:2": __mistral_mapping__,
        "amazon.titan-text-express-v1": __titan_mapping__,
        "amazon.titan-text-lite-v1": __titan_mapping__,
        "meta.llama2-70b-chat-v1": __meta_mapping__,
        "meta.llama2-13b-chat-v1": __meta_mapping__,
        "cohere.command-text-v14": __cohere_mapping__,
        "cohere.command-light-text-v14": __cohere_mapping__,
        "ai21.jamba-instruct-v1:0": __ai21_mapping__,
        "ai21.j2-ultra-v1": __ai21_mapping__,
        "ai21.j2-mid-v1": __ai21_mapping__,
    }

    def __init__(self, params: BedrockParams, model_id: str):
        self._params = params
        self._mapping = self.__maps__[model_id]

    def to_dict(self) -> dict:
        return {
            self._mapping[elem_k]: elem_val
            for elem_k, elem_val in asdict(self._params).items()
            if elem_k in self._mapping
        }


@dataclass
class HfTgiModelParams:
    """
    Parameters for Hugging Face LLM Inference Container for Amazon SageMaker
    Reference: https://huggingface.co/blog/sagemaker-huggingface-llm
    https://huggingface.github.io/text-generation-inference/#/Text%20Generation%20Inference/generate
    """

    temperature: str
    top_p: str
    top_k: str
    do_sample: bool
    max_new_tokens: str
    repetition_penalty: str
    seed: str
    details: bool
    return_full_text: bool
    watermark: str
    stop: str

    def to_dict(self):
        return asdict(self)


@dataclass
class HfTransformersModelParams:
    """
    Parameters for classic HF Transformer Container and for LMI container (i.e. non TGI Containers).
    Reference: https://huggingface.co/docs/transformers/v4.29.1/en/main_classes/text_generation#transformers.GenerationConfig
    """

    temperature: str
    top_p: str
    top_k: str
    max_new_tokens: str
    repetition_penalty: str

    def to_dict(self):
        return asdict(self)
