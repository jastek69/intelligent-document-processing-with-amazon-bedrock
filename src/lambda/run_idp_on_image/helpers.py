"""
Copyright © Amazon.com and Affiliates
"""

from io import BytesIO
from typing import Any, Union

from pdf2image import convert_from_path
import json


def get_base64_encoded_images_from_pdf(pdf_file_path) -> list[bytes]:
    """
    Convert PDF pages to base64-encoded JPEG images.

    Args:
        pdf_file_path (str): Path to the PDF file to convert

    Returns:
        list[bytes]: List of byte strings representing JPEG images, one per PDF page
    """
    images = convert_from_path(pdf_file_path)
    bytes_strs = []
    for image in images:
        buffered = BytesIO()
        image.save(buffered, format="JPEG")
        bytes_strs.append(buffered.getvalue())
    return bytes_strs


def fill_assistant_response_template(marking_json: dict) -> str:
    """
    Fill the assistant response template with marking JSON data

    Args:
        marking_json (dict): JSON data containing the marking information

    Returns:
        str: Formatted response string with thinking and JSON sections
    """
    return f"<thinking>\nI was able to find all the requested attributes\n</thinking>\n<json>\n{json.dumps(marking_json)}\n</json>\n"  # noqa: E501


def create_assistant_response(marking_file: str, original_file: str) -> dict:
    """
    Create an assistant response from marking file data

    Args:
        marking_file (str): Path to the JSON file containing marking data
        original_file (str): Path to the original file to find in marking data

    Returns:
        dict: Assistant message format with role "assistant" and formatted content
    """
    file_key = original_file.split("/")[-1]
    content = None
    with open(marking_file, encoding="utf-8") as f:
        marking_json = json.load(f)
        if isinstance(marking_json, list):
            for item in marking_json:
                if item["file"].split("/")[-1] == file_key:
                    content = [{"text": fill_assistant_response_template(item["output"])}]
                    break
        else:
            if marking_json["file"].split("/")[-1] != file_key:
                raise ValueError("File key in marking file does not match the provided file.")
            content = [
                {
                    "text": fill_assistant_response_template(marking_json["output"]),
                }
            ]

    if content is None:
        raise ValueError("File key not found in marking file.")
    return {"role": "assistant", "content": content}


def combine_json_responses(responses: list) -> dict:
    """
    Combines multiple JSON responses into a single response.

    Args:
        responses (list): List of dictionaries to combine

    Returns:
        dict: Combined JSON response
    """
    combined_json = {}
    for response in responses:
        if not isinstance(response, dict):
            continue

        for key, value in response.items():
            if key not in combined_json:
                combined_json[key] = value
            elif isinstance(value, list) and isinstance(combined_json[key], list):
                # Both are lists, extend the existing list
                combined_json[key].extend(value)
            elif not isinstance(value, list) and not isinstance(combined_json[key], list):
                # Both are primitives (strings, numbers, etc.), make a list
                combined_json[key] = [combined_json[key], value]
            elif not isinstance(value, list) and isinstance(combined_json[key], list):
                # Existing is list, new is primitive, append to list
                combined_json[key].append(value)
            elif isinstance(value, list) and not isinstance(combined_json[key], list):
                # Existing is primitive, new is list, combine into new list
                combined_json[key] = [combined_json[key]] + value
    return combined_json


def create_human_message_with_imgs(text: str, file: Union[str, None] = None, max_pages: int = 20) -> dict[str, Any]:
    """
    Create a human message with embedded images for conversation API

    Args:
        text (str): The text message to include
        file (str, optional): Path to the image or PDF file. Defaults to None.
        max_pages (int): Maximum number of pages/images to include. Defaults to 20.

    Returns:
        dict: Message format with role "user" and content containing images and text
    """
    content: list[dict[str, Any]] = []
    if file:
        if file.lower().endswith(".pdf"):
            bytes_strs = get_base64_encoded_images_from_pdf(file)
            format = "jpeg"
        elif file.lower().endswith((".jpeg", ".jpg", ".png")):
            with open(file, "rb") as image_file:
                binary_data = image_file.read()
                bytes_strs = [binary_data]
            format = "png" if file.lower().endswith(".png") else "jpeg"

        bytes_strs = bytes_strs[:max_pages]
        if not bytes_strs:
            raise ValueError(
                "No images found in the file. Consider uploading a different file or adjust cutoff settings."
            )

        for bytes_str in bytes_strs:
            content.append(
                {
                    "image": {
                        "format": format,
                        "source": {
                            "bytes": bytes_str,
                        },
                    },
                },
            )
    content.append({"text": text})
    return {"role": "user", "content": content}


def create_human_message_with_imgs_generator(
    text: str, file: Union[str, None] = None, max_pages: int = 20, start_page: int = 0
):
    """
    Create a generator that yields human messages with chunked images and text.

    Args:
        text (str): The text message to include
        file (str, optional): Path to the image or PDF file. Defaults to None.
        max_pages (int): Maximum number of images per chunk. Defaults to 20.
        start_page (int): Starting page/image index. Defaults to 0.

    Yields:
        dict: Message format compatible with the conversation API
    """
    if not file:
        yield {"role": "user", "content": [{"text": text}]}
        return

    # get base64 encoded images
    if file.lower().endswith(".pdf"):
        bytes_strs = get_base64_encoded_images_from_pdf(file)
        format = "jpeg"
    elif file.lower().endswith((".jpeg", ".jpg", ".png")):
        with open(file, "rb") as image_file:
            binary_data = image_file.read()
            bytes_strs = [binary_data]
        format = "png" if file.lower().endswith(".png") else "jpeg"
    else:
        raise ValueError("Unsupported file format")

    # validate images
    if not bytes_strs:
        raise ValueError("No images found in the file. Consider uploading a different file or adjust cutoff settings.")

    # skip to start_page
    bytes_strs = bytes_strs[start_page:]

    # yield chunks of images
    for i in range(0, len(bytes_strs), max_pages):
        chunk = bytes_strs[i : i + max_pages]
        content: list[dict[str, Any]] = []

        # add images for this chunk
        for bytes_str in chunk:
            content.append(
                {
                    "image": {
                        "format": format,
                        "source": {
                            "bytes": bytes_str,
                        },
                    },
                },
            )

        # add text with page range information if there are multiple chunks
        chunk_text = text
        if len(bytes_strs) > max_pages:
            page_range = f"Processing pages {start_page + i + 1}:{start_page + i + len(chunk)}"
            chunk_text = f"{page_range}. {text}"

        content.append({"text": chunk_text})
        yield {"role": "user", "content": content}
