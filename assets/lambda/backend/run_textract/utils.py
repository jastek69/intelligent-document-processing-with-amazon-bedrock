"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Textract utilities
"""

import logging
import os
import re
from typing import Dict, Tuple

import pandas as pd
import s3fs
from textractor.data.markdown_linearization_config import MarkdownLinearizationConfig
from textractor.data.text_linearization_config import TextLinearizationConfig
from textractor.entities.document import Document

config_kwargs = {
    "table_flatten_headers": os.environ["TABLE_FLATTEN_HEADERS"],
    "table_remove_column_headers": os.environ["TABLE_REMOVE_COLUMN_HEADERS"],
    "table_duplicate_text_in_merged_cells": os.environ["TABLE_DUPLICATE_TEXT_IN_MERGED_CELLS"],
    "hide_footer_layout": os.environ["HIDE_FOOTER_LAYOUT"],
    "hide_header_layout": os.environ["HIDE_HEADER_LAYOUT"],
    "hide_page_num_layout": os.environ["HIDE_PAGE_NUM_LAYOUT"],
}

TEXT_CONFIG = TextLinearizationConfig(**config_kwargs)
MARKDOWN_CONFIG = MarkdownLinearizationConfig(**config_kwargs)


def clean_text_snippet(text: str, max_length: int = None) -> str:
    """
    Clean a text snippet

    Parameters
    ----------
    text : str
        Text snippet to be cleaned
    max_length : None
        Maximum no. characters in the text snippet, by default None
    Returns
    -------
    str
        Cleaned text snippet
    """

    special_symbols = ["™", "®", "©"]
    for sym in special_symbols:
        text = re.sub(sym, "", text)

    text = text.strip()

    if max_length is not None:
        if max_length > len(text):
            text = f"{text[:max_length]}..."

    return text


def get_document_text(
    bucket_name: str,
    prefix: str,
    file_name: str,
    max_length: int = None,
) -> str:
    """
    Return document text

    Parameters
    ----------
    bucket_name : str
        S3 bucket name
    prefix : str
        S3 prefix
    file_name : str
        File name
    max_length : None
        Maximum no. characters in the text snippet, by default None
    Returns
    -------
    str
        Cleaned text snippet
    """

    doc_uri = f"{prefix}/{file_name}"

    # read document from S3
    fs = s3fs.S3FileSystem(anon=False)
    try:
        with fs.open(f"{bucket_name}/{doc_uri}", "rb", encoding="utf-8") as f:
            s3_object = f.read()
    except:  # noqa: E722
        print(f"Could not find {doc_uri} in {bucket_name}")
        return None
    doc_text = s3_object.decode("utf-8")

    return clean_text_snippet(
        text=doc_text,
        max_length=max_length,
    )


def compile_tables(document: Document, logger: logging.Logger) -> Dict:
    """
    function to compile all tables in a parsed textractor.entities.document
    if a table has a new title, has new column names that are not the default [1,2,3,...,n]
    or has a different column count than the preceding table, it is considered a new table
    otherwise, it is a continuation of the preceding table when page breaks,
    it is appended to the preceding table

    Parameters
    ----------
    document : textractor.entities.document.Document
        the parsed document
    logger: logging.Logger
        logger object passed from the lambda
    Returns
    -------
    Dict
        dictionary of all tables present in the document
    """
    all_tables = {}
    kwargs = {
        "use_columns": True,
        "config": TEXT_CONFIG,
    }

    last_valid_table_columns = []
    last_title = ""
    for i, table in enumerate(document.tables):
        if bool(table.title):
            new_title = " ".join(str(w) for w in table.title.words)
            print(f"Detected new table title: {new_title}")
            table_page_layout = document.pages[table.page - 1].page_layout
            table_page_title = table_page_layout.titles.get_text()
            table_page_header = table_page_layout.headers.get_text()
            logger.debug(f"Table belongs to page titled '{table_page_title}' & header '{table_page_header}'...")
            duplicate_title = table_page_title.find(new_title) != -1
            duplicate_header = table_page_header.find(new_title) != -1
            if duplicate_title or duplicate_header:
                new_title = f"table_{i+1}"
        else:
            new_title = f"table_{i+1}"
        logger.debug(f"Final new table title: {new_title}")

        pandas_table = table.to_pandas(**kwargs)
        logger.debug(f"New column values: {pandas_table.columns.values}")

        if (
            (new_title == last_title or new_title == f"table_{i+1}")
            and table.column_count == len(last_valid_table_columns)
            and (
                all(pandas_table.columns.values == last_valid_table_columns)
                or all(pandas_table.columns.values == list(range(table.column_count)))
            )
        ):
            # table has the same non-empty title
            # and the same column names as last table
            # or table has header [0,1,2,..., len(last_valid_table_columns)]
            logger.debug(f"Appending to previous {last_title} table...")
            pandas_table.columns = last_valid_table_columns
            all_tables[last_title] = pd.concat(
                [all_tables[last_title], pandas_table],
                axis=0,
                ignore_index=True,
            )

        else:
            # table has new title, or new column names or different column count:
            logger.debug(f"Creating new {new_title} table...")
            all_tables[new_title] = pandas_table
            last_valid_table_columns = pandas_table.columns.values
            last_title = new_title
        logger.debug("\n======================\n")
    return all_tables


def extract_content_by_pages(document: Document, logger: logging.Logger) -> Tuple:
    """
    function to separate Textractor output into raw markdown content and tables

    Parameters
    ----------
    document : textractor.entities.document.Document
        the parsed document
    logger: logging.Logger
        logger object passed from the lambda
    Returns
    -------
    Tuple(str,Dict)
        (markdown content, table content)
    """
    md_content = document.get_text(config=MARKDOWN_CONFIG)
    md_content_tight = re.sub(r"\n+", "\n", md_content).strip()
    table_content = compile_tables(document, logger)
    return md_content_tight, table_content


def check_file_extension(filename: str) -> bool:
    if filename.lower().endswith(".pdf", ".txt", ".png", ".jpg", ".tiff", ".jpeg", ".tif"):
        return True
    return False
