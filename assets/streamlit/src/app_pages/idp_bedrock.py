"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Streamlit frontend
"""

#########################
#    IMPORTS & LOGGER
#########################

import asyncio
import datetime
import json
import logging
import os
import sys
from typing import List

from components.ssm import load_ssm_params
from dotenv import dotenv_values, load_dotenv

# for local testing only
if "COVER_IMAGE_URL" not in os.environ:
    try:
        stack_name = dotenv_values()["STACK_NAME"]
    except Exception as e:
        print("Error. Make sure to add STACK_NAME in .env file")
        raise e

    # Load SSM Parameters as env variables
    print("Loading env variables from SSM Parameters")
    path_prefix = f"/{stack_name}/ecs/"
    load_ssm_params(path_prefix)
    # Overwrite env variables with the ones defined in .env file
    print("Loading env variables from .env file")
    load_dotenv(override=True)

import components.api as api
import components.authenticate as authenticate
import pandas as pd
import streamlit as st
from components.constants import (
    DEFAULT_ATTRIBUTES,
    DEFAULT_DOCS,
    DEFAULT_FEW_SHOTS,
    MAX_ATTRIBUTES,
    MAX_CHARS_DESCRIPTION,
    MAX_CHARS_DOC,
    MAX_CHARS_FEW_SHOTS_INPUT,
    MAX_CHARS_FEW_SHOTS_OUTPUT,
    MAX_CHARS_NAME,
    MAX_DOCS,
    MAX_FEW_SHOTS,
    OFFICE_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_EXTENSIONS_BEDROCK,
    TEMPERATURE_DEFAULT,
)
from components.frontend import show_empty_container, show_footer
from components.model import get_model_names
from components.s3 import create_presigned_url
from components.styling import set_page_styling
from st_pages import add_indentation, show_pages_from_config

LOGGER = logging.Logger("Streamlit", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)

authenticate.set_st_state_vars()


#########################
#     COVER & CONFIG
#########################

# titles
COVER_IMAGE_URL = os.environ.get("COVER_IMAGE_URL")
COVER_IMAGE = create_presigned_url(COVER_IMAGE_URL)
ASSISTANT_AVATAR = os.environ.get("ASSISTANT_AVATAR_URL")
PAGE_TITLE = "IDP Bedrock"
PAGE_ICON = ":sparkles:"

# page config
st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="centered",
    initial_sidebar_state="expanded",
)

# page width, form borders, message styling
style_placeholder = st.empty()
with style_placeholder:
    set_page_styling()

# display cover
cover_placeholder = st.empty()
with cover_placeholder:
    st.markdown(
        f'<img src="{COVER_IMAGE}" width="100%" style="margin-left: auto; margin-right: auto; display: block;">',
        unsafe_allow_html=True,
    )

# custom page names in the sidebar
add_indentation()
show_pages_from_config()


#########################
#      CHECK LOGIN
#########################

# check authentication
authenticate.set_st_state_vars()

# switch to home page if not authenticated
if not st.session_state["authenticated"]:
    st.switch_page("Home.py")


#########################
#       CONSTANTS
#########################

BEDROCK_MODEL_IDS = json.loads(os.environ.get("BEDROCK_MODEL_IDS"))
MODEL_SPECS = get_model_names(BEDROCK_MODEL_IDS)

RUN_EXTRACTION = False


#########################
#     SESSION STATE
#########################

st.session_state.setdefault("authenticated", "False")
st.session_state.setdefault("parsed_response", [])
st.session_state.setdefault("raw_response", [])
st.session_state.setdefault("texts", [])
st.session_state.setdefault("num_docs", DEFAULT_DOCS)
st.session_state.setdefault("num_attributes", DEFAULT_ATTRIBUTES)
st.session_state.setdefault("num_few_shots", DEFAULT_FEW_SHOTS)
st.session_state.setdefault("docs_uploader_key", 0)
st.session_state.setdefault("attributes_uploader_key", 0)
st.session_state.setdefault("few_shots_uploader_key", 0)


#########################
#    HELPER FUNCTIONS
#########################


def clear_results() -> None:
    """
    Clear results
    """
    st.session_state["parsed_response"] = []
    st.session_state["raw_response"] = []
    st.session_state["docs"] = []
    st.session_state["attributes"] = []
    st.session_state["few_shots"] = []
    st.session_state["num_attributes"] = DEFAULT_ATTRIBUTES
    st.session_state["num_docs"] = DEFAULT_DOCS
    st.session_state["num_few_shots"] = DEFAULT_FEW_SHOTS
    st.session_state["docs_uploader_key"] += 1
    st.session_state["attributes_uploader_key"] += 1
    st.session_state["few_shots_uploader_key"] += 1
    for i in range(MAX_DOCS):
        if f"document_{i}" in st.session_state:
            st.session_state[f"document_{i}"] = ""
    for i in range(MAX_ATTRIBUTES):
        if f"name_{i}" in st.session_state:
            st.session_state[f"name_{i}"] = ""
        if f"description_{i}" in st.session_state:
            st.session_state[f"description_{i}"] = ""
    LOGGER.info(("Clearing results"))


def show_attribute_fields(idx: int) -> None:
    """
    Show input fields for entity description
    """
    col1, col2 = st.columns([0.25, 0.75])

    example_names = ["Person", "English", "Sentiment"]
    example_placeholders = [
        "Name of any person who is mentioned in the document",
        "Whether the document is written in English",
        "Overall sentiment of the text between 0 and 1",
    ]

    with col1:
        name = st.text_area(
            placeholder=example_names[idx % len(example_names)],
            label="Name:",
            label_visibility="collapsed" if idx != 0 else "visible",
            key=f"name_{idx}",
            height=30,
            max_chars=MAX_CHARS_NAME,
        )
    with col2:
        description = st.text_area(
            placeholder=example_placeholders[idx % len(example_placeholders)],
            label="Description:",
            label_visibility="collapsed" if idx != 0 else "visible",
            key=f"description_{idx}",
            height=30,
            max_chars=MAX_CHARS_DESCRIPTION,
        )

    return {
        "name": name,
        "description": description,
    }


def fill_attribute_fields(idx: int) -> None:
    """
    Fill input fields for entity description
    """
    col1, col2 = st.columns([0.25, 0.75])

    with col1:
        name = st.text_area(
            label="Name:",
            label_visibility="collapsed" if idx != 0 else "visible",
            key=f"name_{idx}",
            height=25,
            max_chars=MAX_CHARS_NAME,
            value=st.session_state["attributes"][idx]["name"],
        )
    with col2:
        description = st.text_area(
            label="Description:",
            label_visibility="collapsed" if idx != 0 else "visible",
            key=f"description_{idx}",
            height=25,
            max_chars=MAX_CHARS_DESCRIPTION,
            value=st.session_state["attributes"][idx]["description"],
        )

    return {
        "name": name,
        "description": description,
    }


def show_few_shots_fields(idx: int) -> None:
    """
    Show input fields for few shots
    """

    col1, col2 = st.columns([0.5, 0.5])
    _exemplar_output = """{
    "Attribute_1": "The correct value of Attribute_1",
    "Attribute_2": "The correct value of Attribute_2",
}"""

    with col1:
        few_shots_input = st.text_area(
            placeholder="Exemplar Input",
            label="Input:",
            label_visibility="collapsed" if idx != 0 else "visible",
            key=f"few_shots_input_{idx}",
            height=120,
            max_chars=MAX_CHARS_FEW_SHOTS_INPUT,
        )
    with col2:
        few_shots_output = st.text_area(
            placeholder=_exemplar_output,
            label="Output:",
            label_visibility="collapsed" if idx != 0 else "visible",
            key=f"few_shots_output_{idx}",
            height=120,
            max_chars=MAX_CHARS_FEW_SHOTS_OUTPUT,
        )

    return {
        "input": few_shots_input,
        "output": few_shots_output,
    }


def fill_few_shots_fields(idx: int) -> None:
    """
    Fill input fields for few shots
    """
    col1, col2 = st.columns([0.5, 0.5])

    with col1:
        few_shots_input = st.text_area(
            label="Input:",
            label_visibility="collapsed" if idx != 0 else "visible",
            key=f"few_shots_input_{idx}",
            height=120,
            max_chars=MAX_CHARS_FEW_SHOTS_INPUT,
            value=json.dumps(st.session_state["few_shots"][idx]["input"], indent=4),
        )
    with col2:
        few_shots_output = st.text_area(
            label="Output:",
            label_visibility="collapsed" if idx != 0 else "visible",
            key=f"few_shots_output_{idx}",
            height=120,
            max_chars=MAX_CHARS_FEW_SHOTS_OUTPUT,
            value=json.dumps(st.session_state["few_shots"][idx]["output"], indent=4),
        )

    return {
        "input": few_shots_input,
        "output": few_shots_output,
    }


def process_response(parsed_response: list, wide=True) -> dict:
    """
    Process JSON file returned by IDP Bedrock
    """
    output_dict = {}

    for idx, dict in enumerate(parsed_response):
        for key in dict:
            if isinstance(dict[key], list):
                dict[key] = str(dict[key])
        output_dict[idx] = dict

    input_dict = output_dict.copy()
    output_dict = {}

    if wide:
        for key in input_dict:
            output_dict[f"doc_{key+1}"] = input_dict[key]

    else:
        docs = [idx + 1 for idx in list(input_dict.keys())]
        output_dict["_doc"] = docs

        attributes = set()
        for v in input_dict.values():
            attributes.update(v.keys())

        for attr in sorted(attributes):
            output_dict[attr] = []

        for doc_idx in docs:
            for attr in attributes:
                value = input_dict[doc_idx - 1].get(attr)
                output_dict[attr].append(value)

    return output_dict


async def upload_file_async(doc, access_token: str, doc_idx: int) -> tuple[int, str]:
    """Helper function to upload a single file asynchronously"""
    file_key = await api.invoke_file_upload_async(file=doc, access_token=access_token)
    return (doc_idx, file_key)


async def upload_all_files_async(docs, access_token: str, progress_callback) -> List[str]:
    """Upload all files concurrently and update progress"""
    file_keys = [""] * len(docs)
    tasks = [upload_file_async(doc, access_token, idx) for idx, doc in enumerate(docs)]

    completed = 0
    total = len(docs)
    for task in asyncio.as_completed(tasks):
        doc_idx, file_key = await task
        completed += 1
        file_keys[doc_idx] = file_key
        progress_callback(completed, total)
        LOGGER.info(f"File {doc_idx + 1} uploaded with key: {file_key}")

    return file_keys


def run_extraction() -> None:
    LOGGER.info("Inside run_extraction()")

    st.session_state["parsed_response"] = []
    st.session_state["raw_response"] = []
    st.session_state["model_id"] = MODEL_SPECS[st.session_state["ai_model"]]
    LOGGER.info(f"Model ID: {st.session_state['model_id']}")

    if len(st.session_state["docs"]) > 1:
        analyze_message = "Analyzing documents in parallel..."
    else:
        analyze_message = "Analyzing the document..."

    # Create persistent containers for status and errors
    status_container = st.empty()
    error_container = st.container()
    thinking = st.empty()
    vertical_space = show_empty_container()

    with thinking.container():
        with st.chat_message(name="assistant", avatar=ASSISTANT_AVATAR):
            upload_message = st.empty()

            try:

                def update_spinner_message(current, total):
                    upload_message.write(f"Uploading documents in parallel... {current}/{total} completed.")

                with st.spinner():
                    file_keys = asyncio.run(
                        upload_all_files_async(
                            st.session_state["docs"], st.session_state["access_tkn"], update_spinner_message
                        )
                    )

                with st.spinner(analyze_message):
                    api.invoke_step_function(
                        file_keys=file_keys,
                        attributes=st.session_state["attributes"],
                        instructions=st.session_state.get("instructions", ""),
                        few_shots=st.session_state.get("few_shots", []),
                        model_id=st.session_state["model_id"],
                        parsing_mode=st.session_state["parsing_mode"],
                        temperature=float(st.session_state["temperature"]),
                    )
            except Exception as e:
                with error_container:
                    error_message = str(e)
                    if "does not support images" in error_message:
                        st.error(
                            "Error: The selected model does not support image processing. Please choose a different model.",
                            icon="🚨",
                        )
                    else:
                        st.error(f"Error: {error_message}", icon="🚨")
            finally:
                thinking.empty()
                vertical_space.empty()

    # Display final status
    if not st.session_state.get("parsed_response"):
        with error_container:
            st.error("No results were generated. Please try again.", icon="🚨")


#########################
#       SIDEBAR
#########################

# sidebar
with st.sidebar:
    st.header("Settings")
    st.subheader("Information Extraction")
    st.selectbox(
        label="Parsing algorithm:",
        options=["Bedrock Data Automation", "Amazon Bedrock LLM", "Amazon Textract"],
        key="parsing_mode",
    )
    st.selectbox(
        label="Language model:",
        options=list(MODEL_SPECS.keys()),
        key="ai_model",
        disabled=st.session_state["parsing_mode"] == "Bedrock Data Automation",
    )
    st.slider(
        label="Temperature:",
        value=TEMPERATURE_DEFAULT,
        min_value=0.0,
        max_value=1.0,
        key="temperature",
        disabled=st.session_state["parsing_mode"] == "Bedrock Data Automation",
    )
    st.markdown("")
    st.subheader("Additional Inputs")
    st.checkbox(
        label="Enable advanced mode",
        key="advanced_mode",
        help="Allows adding document-level instructions and few-shot examples to improve extraction accuracy",
        disabled=st.session_state["parsing_mode"] == "Bedrock Data Automation",
    )
    st.markdown("")
    st.subheader("Output Format")
    st.radio(
        label="Table format:",
        options=["Long", "Wide"],
        key="table_format",
    )

    with st.expander(":question: Read more"):
        st.markdown(
            """- **Language model**: which foundation model is used to analyze the document. Various models may have different accuracy and answer latency.
- **Temperature**: temperature controls model creativity. Higher values results in more creative answers, while lower values make them more deterministic.
- **Advanced mode**: allows providing optional document-level instructions and few-shot examples as inputs.
- **Table format**: the format of the output table. Long format shows attributes as columns and documents as rows."""  # noqa: E501
        )

# info banner
with st.expander(":bulb: You are interacting with Generative AI enabled system. Expand to show instructions."):
    st.markdown(
        """- This app extracts custom attributes from your documents using LLMs
- Please specify extraction parameters and provide the inputs
- Upload your docs or insert texts on the **"Add Docs"** tab
- Describe attributes to be extracted on the **"Describe Attributes"** tab
- Optionally, provide additional instructions in **Instructions (optional)** tab (if enabled)
- Optionally, provide few shot examples in **Few Shots (optional)** tab (if enabled)
- Select the LLM and the output format using the left sidebar
- Press **"Extract attributes"** once you have entered all input data
"""
    )


#########################
#       MAIN PAGE
#########################

# tab layout
tabs = [
    ":scroll: **1. Add Docs**",
    ":sparkles: **2. Describe Attributes**",
    ":heavy_plus_sign: **3. Instructions (optional)**",
    ":books: **4. Examples (optional)**",
]
if st.session_state["advanced_mode"]:
    tab_docs, tab_attributes, tab_instructions, tab_few_shots = st.tabs(tabs)
else:
    tab_docs, tab_attributes = st.tabs(tabs[:2])

# documents
with tab_docs:
    st.radio(
        label="Please provide the input documents by uploading the files or entering the texts manually.",
        label_visibility="visible",
        key="docs_input_type",
        options=["Upload documents", "Enter texts manually"],
    )
    if st.session_state["docs_input_type"] == "Upload documents":
        if st.session_state["parsing_mode"] == "Bedrock Data Automation":
            st.warning("Parsing with Bedrock Data Automation only supports PDF files up to 20 pages.")
        if st.session_state["parsing_mode"] == "Amazon Bedrock LLM":
            st.warning(f"Parsing with Amazon Bedrock only supports selected Claude and Nova LLMs and {', '.join([x.upper() for x in SUPPORTED_EXTENSIONS_BEDROCK])} files.")
        files = st.file_uploader(
            label="Upload your document(s):",
            accept_multiple_files=True,
            key=f"{st.session_state['docs_uploader_key']}",
            type=["pdf"] if st.session_state["parsing_mode"] == "Bedrock Data Automation"
            else SUPPORTED_EXTENSIONS_BEDROCK
            if st.session_state["parsing_mode"] == "Amazon Bedrock LLM"
            else SUPPORTED_EXTENSIONS,
        )
        for file in files:
            if any([file.name.endswith(i) for i in OFFICE_EXTENSIONS]):
                st.info("ℹ️ Only text content from Office documents is used. Convert to PDF to process visual information.")
            break
        st.session_state["docs"] = files[::-1]
    else:
        docs_placeholder = st.empty()
        col_add, col_remove, _ = st.columns([0.11, 0.12, 0.70])
        with col_add:
            if st.button(
                ":heavy_plus_sign: Add",
                key="add_doc",
                disabled=st.session_state["num_docs"] == MAX_DOCS,
                use_container_width=True,
            ):
                st.session_state["num_docs"] += 1
        with col_remove:
            if st.button(
                ":heavy_minus_sign: Remove",
                key="remove_doc",
                disabled=st.session_state["num_docs"] == 1,
                use_container_width=True,
            ):
                st.session_state["num_docs"] = max(1, st.session_state["num_docs"] - 1)
        with docs_placeholder.container():
            st.session_state["docs"] = []
            for idx in range(st.session_state["num_docs"]):
                text = st.text_area(
                    placeholder="Please enter the text",
                    label="Enter your text(s):",
                    label_visibility="visible" if idx == 0 else "collapsed",
                    key=f"document_{idx}",
                    height=100,
                    max_chars=MAX_CHARS_DOC,
                )
                if text.strip():
                    st.session_state["docs"].append(text)
    LOGGER.info(f"Docs: {st.session_state['docs']}")

# attributes
with tab_attributes:
    st.radio(
        label="Please provide the attributes to be extracted, including name and description (e.g. explanation, possible values, examples).",  # noqa: E501
        label_visibility="visible",
        key="attributes_input_type",
        options=["Upload attributes", "Enter attributes manually"],
        index=1,
    )
    if st.session_state["attributes_input_type"] == "Upload attributes":
        st.markdown(
            "Note: the attributes must be formatted as JSON list and contain two fields: **name** and **description**"  # noqa: E501
        )
        attributes = st.file_uploader(
            label="Upload your attributes:",
            accept_multiple_files=False,
            key=f"attributes_{st.session_state['attributes_uploader_key']}",
            type=["json"],
        )
        attributes_placeholder = st.empty()
        if attributes is not None:
            with attributes_placeholder.container():
                st.session_state["attributes"] = json.load(attributes)
                st.session_state["num_attributes"] = len(st.session_state["attributes"])
                for idx in range(st.session_state["num_attributes"]):
                    entity_dict = fill_attribute_fields(idx)
    else:
        attributes_placeholder = st.empty()
        col_add, col_remove, _ = st.columns([0.11, 0.12, 0.70])
        with col_add:
            if st.button(
                ":heavy_plus_sign: Add",
                key="add_attribute",
                disabled=st.session_state["num_attributes"] == MAX_ATTRIBUTES,
                use_container_width=True,
            ):
                st.session_state["num_attributes"] += 1
        with col_remove:
            if st.button(
                ":heavy_minus_sign: Remove",
                key="remove_attribute",
                disabled=st.session_state["num_attributes"] == 1,
                use_container_width=True,
            ):
                st.session_state["num_attributes"] = max(1, st.session_state["num_attributes"] - 1)
        with attributes_placeholder.container():
            st.session_state["attributes"] = []
            for idx in range(st.session_state["num_attributes"]):
                entity_dict = show_attribute_fields(idx)
                if entity_dict["name"].strip() and entity_dict["description"].strip():
                    st.session_state["attributes"].append(entity_dict)
    LOGGER.info(f"Attributes: {st.session_state['attributes']}")

# instructions
if st.session_state["advanced_mode"]:
    with tab_instructions:
        instructions = st.text_area(
            placeholder="Please enter the instructions",
            label="You can provide optional document-level instructions such as formatting descriptions.",  # noqa: E501
            label_visibility="visible",
            key="instructions",
            height=150,
            max_chars=MAX_CHARS_DESCRIPTION,
        )
else:
    st.session_state["instructions"] = ""

# examples
if st.session_state["advanced_mode"]:
    multimodal_on = st.session_state["parsing_mode"] == "Amazon Bedrock LLM"
    with tab_few_shots:
        if not multimodal_on:
            st.radio(
                label="Please provide few-shot examples",  # noqa: E501
                label_visibility="visible",
                key="few_shots_input_type",
                options=["Upload few shots", "Enter few shots manually"],
                index=1,
            )
        if multimodal_on or st.session_state["few_shots_input_type"] == "Upload few shots":
            if multimodal_on:
                st.markdown(
                    (
                        "Note: examples must be formatted as JSON list and contain two fields: **file** and **output**."  # noqa: E501
                        "\n\n**file** must be a name of file from the list of uploaded files."  # noqa: E501
                        "\n\n**output** must be a dictionary with the same key as the attributes you want to extract."  # noqa: E501
                    )
                )
                col1, col2 = st.columns([0.5, 0.5])
                with col1:
                    # upload one pdf per example
                    few_shots_docs = st.file_uploader(
                        label="Upload your pdf marked file:",
                        accept_multiple_files=True,
                        key=f"few_shots_pdfs_{st.session_state['few_shots_uploader_key']}",
                        type=["pdf", "png", "jpg"],
                    )
                    file_keys_few_shots = []
                    for doc_idx, doc in enumerate(few_shots_docs):
                        with st.spinner(f"Uploading document {doc_idx + 1}/{len(few_shots_docs)}..."):
                            file_key = api.invoke_file_upload(
                                file=doc, prefix="few_shots", access_token=st.session_state["access_tkn"]
                            )
                            file_keys_few_shots.append(file_key)
                            LOGGER.info(f"file key: {file_key}")
                with col2:
                    # upload json with markings
                    few_shots = st.file_uploader(
                        label="Upload your json file which contains correct model's outputs:",
                        accept_multiple_files=False,
                        key=f"few_shots_{st.session_state['few_shots_uploader_key']}",
                        type=["json"],
                    )
                    if few_shots is not None:
                        with st.spinner("Uploading examples..."):
                            file_key_markings = api.invoke_file_upload(
                                file=few_shots, prefix="few_shots", access_token=st.session_state["access_tkn"]
                            )
                            LOGGER.info(f"file key: {file_key_markings}")
            else:
                st.markdown(
                    (
                        "Note: examples must be formatted as JSON list and contain two fields: **input** and **output**."  # noqa: E501
                        "\n\n**output** must be a dictionary with the same key as the attributes you want to extract."  # noqa: E501
                    )
                )
                few_shots = st.file_uploader(
                    label="Upload your examples:",
                    accept_multiple_files=False,
                    key=f"few_shots_{st.session_state['few_shots_uploader_key']}",
                    type=["json"],
                )
                # if few_shots is not None:
                #     with st.spinner("Uploading examples..."):
                #         # TODO: look into the behaviour when not using deepcopy here (few_shot variable changes after file upload)
                #         file_key_markings = api.invoke_file_upload(
                #             file=deepcopy(few_shots), prefix="few_shots", access_token=st.session_state["access_tkn"]
                #         )
                #         LOGGER.info(f"file key: {file_key_markings}")

            if few_shots is not None:
                if multimodal_on:
                    # in case of multimodal only file upload is available
                    st.session_state["few_shots"] = {"documents": file_keys_few_shots, "markings": file_key_markings}
                    st.session_state["num_few_shots"] = len(st.session_state["few_shots"]["documents"])
                else:
                    few_shots_placeholder = st.empty()
                    with few_shots_placeholder.container():
                        st.session_state["few_shots"] = json.load(few_shots)
                        st.session_state["num_few_shots"] = len(st.session_state["few_shots"])
                        for idx in range(st.session_state["num_few_shots"]):
                            entity_dict = fill_few_shots_fields(idx)

        else:
            few_shots_placeholder = st.empty()
            col_add, col_remove, _ = st.columns([0.11, 0.12, 0.70])
            with col_add:
                if st.button(
                    ":heavy_plus_sign: Add",
                    key="add_few_shots",
                    disabled=st.session_state["num_few_shots"] == MAX_FEW_SHOTS,
                    use_container_width=True,
                ):
                    st.session_state["num_few_shots"] += 1
            with col_remove:
                if st.button(
                    ":heavy_minus_sign: Remove",
                    key="remove_few_shots",
                    disabled=st.session_state["num_few_shots"] == 0,
                    use_container_width=True,
                ):
                    st.session_state["num_few_shots"] = max(0, st.session_state["num_few_shots"] - 1)

            with few_shots_placeholder.container():
                st.session_state["few_shots"] = []
                for idx in range(st.session_state["num_few_shots"]):
                    entity_dict = show_few_shots_fields(idx)
                    if entity_dict["input"].strip() and entity_dict["output"].strip():
                        st.session_state["few_shots"].append(entity_dict)
        LOGGER.info(f"Few shots: {st.session_state['few_shots']}")
else:
    st.session_state["few_shots"] = []

# action buttons
st.markdown("")
col1, col2, col3 = st.columns([0.20, 0.60, 0.20])
with col1:
    submit_disabled = not any(st.session_state["docs"]) or not any(st.session_state["attributes"])
    if st.button(":rocket: Extract attributes", disabled=submit_disabled, use_container_width=True):
        RUN_EXTRACTION = True
with col3:
    clear_disabled = not any(st.session_state["docs"]) and not st.session_state["parsed_response"]
    for i in range(MAX_ATTRIBUTES):
        if (f"name_{i}" in st.session_state and f"description_{i}" in st.session_state) and (
            st.session_state[f"name_{i}"] or st.session_state[f"description_{i}"]
        ):
            clear_disabled = False
            break
    st.button(":wastebasket: Clear results", on_click=clear_results, disabled=clear_disabled, use_container_width=True)

# show work in progress
if RUN_EXTRACTION:
    LOGGER.info("State")
    for k, v in dict(st.session_state).items():
        LOGGER.info(f"{k}={v}")
    run_extraction()

# show model response
if st.session_state.get("parsed_response"):
    st.markdown("")
    with st.chat_message(name="assistant", avatar=ASSISTANT_AVATAR):
        if st.session_state["parsed_response"]:
            # table with attributes
            st.markdown("Here are the extracted attributes:")
            answer = process_response(
                st.session_state["parsed_response"], wide=st.session_state["table_format"] == "Wide"
            )
            st.dataframe(
                answer,
                hide_index=st.session_state["table_format"] != "Wide",
                use_container_width=False,
                width=850,
                column_config={"_index": "Feature"} if st.session_state["table_format"] == "Wide" else {},
            )

            # download buttons
            file_name = f"idp-bedrock-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            col1, col2, col3 = st.columns([0.125, 0.125, 0.75])
            with col1:
                st.download_button(
                    label=":arrow_down: JSON",
                    data=json.dumps(answer),
                    mime="application/json",
                    file_name=f"{file_name}.json",
                    use_container_width=True,
                )
            with col2:
                st.download_button(
                    label=":arrow_down: CSV",
                    data=pd.DataFrame(answer).to_csv(index=True).encode("utf-8"),
                    mime="text/csv",
                    file_name=f"{file_name}.csv",
                    use_container_width=True,
                )

# show LLM responses
if st.session_state.get("raw_response"):
    with st.expander(":mag: Show full results"):
        for idx, (response, raw_response) in enumerate(
            zip(st.session_state["parsed_response"], st.session_state["raw_response"])
        ):
            file_name = response.get("_file_name", "")
            processed_name = file_name.rsplit(".", 1)[0] + ".txt"
            url_original = create_presigned_url(f"s3://{os.environ.get('BUCKET_NAME')}/originals/{file_name}")
            url_processed = create_presigned_url(f"s3://{os.environ.get('BUCKET_NAME')}/processed/{processed_name}")

            st.markdown(f"##### {idx+1}. {file_name}")
            st.markdown("**Document**")
            if st.session_state["parsing_mode"] != "Bedrock Data Automation":
                st.markdown(
                    f"""
- [Original document]({url_original})
- [Processed document]({url_processed})"""
                )
            else:
                st.markdown(f"""[Original document]({url_original})""")
            st.markdown("")
            st.markdown("**Explanation**")
            st.warning(raw_response.split("<thinking>", 1)[-1].split("</thinking>", 1)[0])
            st.markdown("")
            st.markdown("**JSON output**")
            st.code(raw_response.split("<json>", 1)[-1].split("</json>", 1)[0], language="json")
            if idx < len(st.session_state["parsed_response"]) - 1:
                st.markdown("---")

# footnote
show_footer()
