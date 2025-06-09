from io import BytesIO

from pdf2image import convert_from_path
import json


def get_base64_encoded_images_from_pdf(pdf_file_path):
    images = convert_from_path(pdf_file_path)
    bytes_strs = []
    for image in images:
        buffered = BytesIO()
        image.save(buffered, format="JPEG")
        bytes_strs.append(buffered.getvalue())
    return bytes_strs


def create_human_message_with_imgs(text, file=None, max_pages=20):
    content = []
    if file:
        if file.lower().endswith(".pdf"):
            bytes_strs = get_base64_encoded_images_from_pdf(file)
        elif file.lower().endswith(".jpeg") or file.lower().endswith(".jpg") or file.lower().endswith(".png"):
            with open(file, "rb") as image_file:
                binary_data = image_file.read()
                bytes_strs = [binary_data]

        bytes_strs = bytes_strs[:max_pages]
        if not bytes_strs:
            raise ValueError(
                "No images found in the file. Consider uploading a different file or adjust cutoff settings."
            )

        for bytes_str in bytes_strs:
            content.append(
                {
                    "image": {
                        "format": "jpeg",
                        "source": {
                            "bytes": bytes_str,
                        },
                    },
                },
            )
    content.append({"text": text})
    return {"role": "user", "content": content}


def fill_assistant_response_template(marking_json):
    return f"<thinking>\nI was able to find all the requested attributes\n</thinking>\n<json>\n{json.dumps(marking_json)}\n</json>\n"  # noqa: E501


def create_assistant_response(marking_file, original_file):
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


def combine_json_responses(responses):
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


def create_human_message_with_imgs_generator(text, file=None, max_pages=20, start_page=0):
    """
    Creates a generator that yields human messages with chunked images and text.
    Each chunk contains max_pages images and includes the text message.

    Args:
        text (str): The text message to include
        file (str, optional): Path to the image or PDF file
        max_pages (int): Maximum number of images per chunk
        start_page (int): Starting page/image index

    Yields:
        dict: Message format compatible with the conversation API
    """
    if not file:
        yield {"role": "user", "content": [{"text": text}]}
        return

    # get base64 encoded images
    if file.lower().endswith(".pdf"):
        bytes_strs = get_base64_encoded_images_from_pdf(file)
    elif file.lower().endswith((".jpeg", ".jpg", ".png")):
        with open(file, "rb") as image_file:
            binary_data = image_file.read()
            bytes_strs = [binary_data]
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
        content = []

        # add images for this chunk
        for bytes_str in chunk:
            content.append(
                {
                    "image": {
                        "format": "jpeg",
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
