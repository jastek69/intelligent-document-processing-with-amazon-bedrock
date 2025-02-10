import base64
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
                        }
                    },
                },
            )
    content.append({"text": text})
    return {"role": "user", "content": content}


def fill_assistant_response_template(marking_json):
    return f"<thinking>\nI was able to find all the requested attributes\n</thinking>\n<json>\n{json.dumps(marking_json)}\n</json>\n"


def create_assistant_response(marking_file, original_file):
    file_key = original_file.split("/")[-1]
    content = None
    with open(marking_file) as f:
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
