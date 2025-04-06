"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Parsing helper functions
"""

import ast
import re


def parse_json_string(text: str) -> dict:
    """
    Parse dict from LLM response string
    """
    try:
        text = text.split("<json>", 1)[1].rsplit("</json>", 1)[0].strip()
    except Exception:
        text = text.strip()

    text = re.sub(r"\n\n+", ",", text)

    if not text.startswith("{") and not text.startswith("["):
        text = "{" + text
    if not text.endswith("}") and not text.endswith("]"):
        text = text + "}"

    text = text.replace("}}", "}")
    text = text.replace("{{", "{")

    return ast.literal_eval(text)


def parse_bedrock_response(response: dict) -> str:
    """
    Parse Bedrock converse API output
    """
    replies = response["output"]["message"]["content"]
    if 1 < len(replies):
        replies = [reply for reply in replies if "text" in reply]  # handle claude 3.7
        if len(replies) != 1:
            raise ValueError(f"Model has returned {len(replies)} text blocks in the response.")
    return replies[0]["text"].strip()
