import base64
from io import BytesIO

from pdf2image import convert_from_path
import json


def get_base64_encoded_images_from_pdf(pdf_file_path):
    images = convert_from_path(pdf_file_path)
    base64_img_strs = []
    for image in images:
        buffered = BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue())
        base64_string = img_str.decode("utf-8")
        base64_img_strs.append(base64_string)
    return base64_img_strs


def create_human_message_with_imgs(text, file=None, max_pages=20):
    content = []
    if file:
        if file.lower().endswith(".pdf"):
            base64_img_strs = get_base64_encoded_images_from_pdf(file)
        elif file.lower().endswith(".jpeg") or file.lower().endswith(".jpg") or file.lower().endswith(".png"):
            with open(file, "rb") as image_file:
                binary_data = image_file.read()
                base64_img_str = base64.b64encode(binary_data)
                base64_img_strs = [base64_img_str.decode("utf-8")]

        base64_img_strs = base64_img_strs[:max_pages]
        if not base64_img_strs:
            raise ValueError(
                "No images found in the file. Consider uploading a different file or adjust cutoff settings."
            )

        for base64_img_str in base64_img_strs:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64_img_str,
                    },
                },
            )
    content.append({"type": "text", "text": text})
    return {"role": "user", "content": content}


def fill_assistant_respose_template(marking_json):
    return f"<thinking>\nI was able to find all the requested attributes\n</thinking>\n<json>\n{json.dumps(marking_json)}\n</json>\n"


def create_assistant_response(marking_file, original_file):
    file_key = original_file.split("/")[-1]
    content = None
    with open(marking_file) as f:
        marking_json = json.load(f)
        if isinstance(marking_json, list):
            for item in marking_json:
                if item["file"].split("/")[-1] == file_key:
                    content = [{"type": "text", "text": fill_assistant_respose_template(item["output"])}]
                    break
        else:
            if marking_json["file"].split("/")[-1] != file_key:
                raise ValueError("File key in marking file does not match the provided file.")
            content = [
                {
                    "type": "text",
                    "text": fill_assistant_respose_template(marking_json["output"]),
                }
            ]

    if content is None:
        raise ValueError("File key not found in marking file.")
    return {"role": "assistant", "content": content}
