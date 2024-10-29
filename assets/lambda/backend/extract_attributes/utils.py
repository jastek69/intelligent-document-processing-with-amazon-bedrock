"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Attribute extraction utils
"""

import warnings

from griptape.tokenizers import (
    BedrockClaudeTokenizer,
    BedrockCohereTokenizer,
    BedrockJurassicTokenizer,
    BedrockLlamaTokenizer,
    BedrockTitanTokenizer,
)


def token_count_tokenizer(text: str, model: str) -> int:
    """
    Estimates the token count from the string

    Parameters
    ----------
    text : str
        the string part which needs to be tokenized
    model
        model id currently selected in app

    Returns
    -------
    int
        the estimated token count based on the model
    """
    if model.split(".")[0] == "anthropic":
        tokenizer = BedrockClaudeTokenizer(model="anthropic.claude-")
        token_count = tokenizer.count_tokens(text)

    elif model.split(".")[0] == "mistral":
        tokenizer = BedrockLlamaTokenizer(model="meta.llama2-13b-chat-v1")
        token_count = tokenizer.count_tokens(text)

    elif model.split(".")[0] == "amazon":
        tokenizer = BedrockTitanTokenizer(model="amazon.titan-text-express-v1")
        token_count = tokenizer.count_tokens(text)

    elif model.split(".")[0] == "meta":
        tokenizer = BedrockLlamaTokenizer(model="meta.llama2-13b-chat-v1")
        token_count = tokenizer.count_tokens(text)

    elif model.split(".")[0] == "cohere":
        tokenizer = BedrockCohereTokenizer(model="cohere.command-r-v1:0")
        token_count = tokenizer.count_tokens(text)

    elif model.split(".")[0] == "ai21":
        tokenizer = BedrockJurassicTokenizer(model="ai21.j2-ultra-v1")
        token_count = tokenizer.count_tokens(text)

    else:
        warnings.warn("Currently we support tokenizers [anthropic, amazon, jurassic, meta, cohere, mistralai]")
        tokenizer = BedrockClaudeTokenizer(model="anthropic.claude-")
        token_count = tokenizer.count_tokens(text)
        # raise NotImplementedError
    return token_count


def truncate_document(
    document: str, token_count_total: int, num_token_prompt: int, model: str, max_token_model: int = 8_000
) -> str:
    """
    Truncates the text to the token count

    Parameters
    ----------
    document : str
        document to truncate
    token_count_total : int
        the estimated token count of the filled prompt + document based on the model
    num_token_prompt : int
        the estimated token count of the filled prompt based on the model
    model
        model id currently selected in app
    max_token_model
        max number of tokens the model accepts

    Returns
    -------
    str
        the truncated document
    """
    # split document into words
    doc_words = document.split(" ")

    # find the number of words to truncate text by around the middle of the document
    split_parameter = (token_count_total - max_token_model) // 2 if max_token_model < token_count_total else 0
    mid_point = len(doc_words) // 2

    # truncate document in the middle if there the number of tokens in document + prompt
    # exceeds the max number of input tokens for the models
    multipliers = []
    start, end, step = 1.0, 5.0, 0.1
    while start < end:
        multipliers.append(start)
        start += step

    # truncate document in the middle if there the number of tokens in document + prompt > context window
    # iteratively increase the cut region until the no. tokens is small enough
    for multiplier in multipliers:
        # print(multiplier, num_tokens_doc)
        truncated_doc = (
            " ".join(doc_words[: (mid_point - int(split_parameter * multiplier))])
            + "\n...\n"
            + " ".join(doc_words[(mid_point + int(split_parameter * multiplier)) :])
        )
        num_tokens_doc = token_count_tokenizer(truncated_doc, model)
        if num_tokens_doc < max_token_model - num_token_prompt:
            break

    return truncated_doc


def format_few_shots(few_shots: list = []) -> dict:
    """
    Formats the few shots into a string

    Parameters
    ----------
    few_shots : list
        list of few shots

    Returns
    -------
    str
        the formatted few shots
    """
    few_shots_dic = {}
    for i, shot in enumerate(few_shots):
        few_shots_dic[f"few_shot_input_{i}"] = shot["input"]
        few_shots_dic[f"few_shot_output_{i}"] = shot["output"]

    return few_shots_dic


def filled_prompt(
    few_shots: list = [], attributes: str = "", template: str = "", instructions: str = "", document: str = ""
) -> str:
    """
    Fills the prompt template with the few shots and attributes

    Parameters
    ----------
    few_shots : list
        list of few shots
    attributes : str
        attributes string
    template : str
        unfilled prompt template string
    instructions : str
        instructions string
    document : str
        document string

    Returns
    -------
    str
        the filled prompt template
    """

    few_shots_dic = format_few_shots(few_shots=few_shots)
    return template.format(**few_shots_dic, attributes=attributes, instructions=instructions, document=document)
