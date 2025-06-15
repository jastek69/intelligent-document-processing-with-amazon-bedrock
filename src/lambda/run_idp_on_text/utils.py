"""
Copyright © Amazon.com and Affiliates
"""

from griptape.tokenizers import AmazonBedrockTokenizer


def token_count_tokenizer(text: str, model: str) -> int:
    """
    Count the number of tokens in the given text using the specified model's tokenizer.

    Parameters
    ----------
    text : str
        The text to count tokens for
    model : str
        The model ID to use for tokenization

    Returns
    -------
    int
        The number of tokens in the text
    """
    tokenizer = AmazonBedrockTokenizer(model=model)
    return tokenizer.count_tokens(text)


def get_max_input_token(model: str) -> int:
    """
    Get the maximum input token limit for the specified model.

    Parameters
    ----------
    model : str
        The model ID to get the token limit for

    Returns
    -------
    int
        The maximum number of input tokens supported by the model
    """
    try:
        if not isinstance(model, str):
            raise ValueError("Model parameter must be a string")

        if not model:
            raise ValueError("Model parameter cannot be empty")

        model = model.removeprefix("us.").removeprefix("eu.")

        tokenizer = AmazonBedrockTokenizer(model=model)
        max_tokens = None

        for prefix in AmazonBedrockTokenizer.MODEL_PREFIXES_TO_MAX_INPUT_TOKENS:
            if tokenizer.model.startswith(prefix):
                max_tokens = AmazonBedrockTokenizer.MODEL_PREFIXES_TO_MAX_INPUT_TOKENS[prefix]
                break

        if max_tokens is None:
            print(f"No matching token limit found for model: {model}")
            max_tokens = 100_000

        return max_tokens

    except Exception as e:
        raise Exception(f"Error getting max input tokens: {str(e)}")  # noqa: B904


def truncate_document(
    document: str, token_count_total: int, num_token_prompt: int, model: str, max_token_model: int = 8_000
) -> str:
    """
    Truncates the document to fit within the model's token limit by removing content from the middle.

    Parameters
    ----------
    document : str
        Document to truncate
    token_count_total : int
        The estimated token count of the filled prompt + document based on the model
    num_token_prompt : int
        The estimated token count of the filled prompt based on the model
    model : str
        Model ID currently selected in app
    max_token_model : int, optional
        Max number of tokens the model accepts (default: 8000)

    Returns
    -------
    str
        The truncated document with content removed from the middle
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
