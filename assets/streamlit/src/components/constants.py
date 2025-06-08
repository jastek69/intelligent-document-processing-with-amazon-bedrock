"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Streamlit constants
"""

MAX_ATTRIBUTES = 50
MAX_DOCS = 50
MAX_FEW_SHOTS = 50

MAX_CHARS_DOC = 500_000
MAX_CHARS_NAME = 100
MAX_CHARS_DESCRIPTION = 100_000
MAX_CHARS_FEW_SHOTS_INPUT = 100_000
MAX_CHARS_FEW_SHOTS_OUTPUT = 100_000

TEMPERATURE_DEFAULT = 0.0

DEFAULT_ATTRIBUTES = 1
DEFAULT_DOCS = 1
DEFAULT_FEW_SHOTS = 1

GENERATED_QRCODES_PATH = "tmp/"

SUPPORTED_EXTENSIONS = [
    "txt",
    "pdf",
    "png",
    "jpg",
    "tiff",
    "docx",
    "doc",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
    "html",
    "htm",
    "md",
]

SUPPORTED_EXTENSIONS_BEDROCK = [
    "pdf",
    "png",
    "jpg",
]

SAMPLE_ATTRIBUTES = [
    {
        "name": "Party Names",
        "description": "Names of all parties involved in the contract, including full legal names",
    },
    {
        "name": "Contract Date",
        "description": "The effective date or execution date of the contract",
    },
    {
        "name": "Contract Value",
        "description": "The total monetary value or consideration specified in the contract",
    },
    {
        "name": "Governing Law",
        "description": "The jurisdiction and legal system that governs the enforcement of the contract",
    },
]

SAMPLE_PDFS = ["rental_agreement_contract.pdf", "service_agreement_contract.pdf", "employment_contract.pdf"]
