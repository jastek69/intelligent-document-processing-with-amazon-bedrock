"""
Copyright © Amazon.com and Affiliates
"""

import json

import components.authenticate as authenticate
import streamlit as st
from components.constants import (
    DEFAULT_ATTRIBUTES,
    DEFAULT_DOCS,
    DEFAULT_FEW_SHOTS,
    MAX_ATTRIBUTES,
    MAX_CHARS_DESCRIPTION,
    MAX_CHARS_FEW_SHOTS_INPUT,
    MAX_CHARS_FEW_SHOTS_OUTPUT,
    MAX_CHARS_NAME,
    MAX_DOCS,
)


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
    st.session_state["instructions"] = ""
    for i in range(MAX_DOCS):
        if f"document_{i}" in st.session_state:
            st.session_state[f"document_{i}"] = ""
    for i in range(MAX_ATTRIBUTES):
        if f"name_{i}" in st.session_state:
            st.session_state[f"name_{i}"] = ""
        if f"description_{i}" in st.session_state:
            st.session_state[f"description_{i}"] = ""


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


def show_empty_container(height: int = 100) -> st.container:
    """
    Display empty container to hide UI elements below while thinking

    Parameters
    ----------
    height : int
        Height of the container (number of lines)

    Returns
    -------
    st.container
        Container with large vertical space
    """
    empty_placeholder = st.empty()
    with empty_placeholder.container():
        st.markdown("<br>" * height, unsafe_allow_html=True)
    return empty_placeholder


def show_footer() -> None:
    """
    Show footer with "Sign out" button and copyright
    """

    st.markdown("---")
    footer_col1, footer_col2 = st.columns(2)

    # log out button
    with footer_col1:
        st.button(":bust_in_silhouette: Sign out", on_click=authenticate.sign_out)

    # copyright
    with footer_col2:
        st.markdown(
            "<div style='text-align: right'> © 2024 Amazon Web Services </div>",
            unsafe_allow_html=True,
        )
