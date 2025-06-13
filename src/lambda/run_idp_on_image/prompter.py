"""
Copyright © Amazon.com and Affiliates
"""

from pathlib import Path


PROMPT_FEW_SHOT = """<example>
<document_text_extracted_from_images>
{few_shot_input_placeholder}
</document_text_extracted_from_images>

Attributes to be extracted:
<attributes>
{{attributes}}
</attributes>

<document_level_instructions_placeholder>

Output:
{few_shot_output_placeholder}
</example>

"""

PROMPT_INSTRUCTIONS = """You must follow these additional instructions:
<instructions>
{instructions}
</instructions>
"""


def _load_prompt_template_from_file(filename: str = "prompt.txt") -> str:
    """
    Load the prompt template from a text file

    Parameters
    ----------
    filename : str, by default "prompt.txt"
        Name of the file to load the template from

    Returns
    -------
    str
        The prompt template content
    """
    current_dir = Path(__file__).parent
    prompt_file_path = current_dir / filename

    try:
        with open(prompt_file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                raise ValueError(f"Template file {filename} is empty")
            return content
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Template file not found at {prompt_file_path}") from e
    except Exception as e:
        raise Exception(f"Error reading template file {filename}: {e}") from e


def load_system_prompt() -> str:
    """
    Load the system prompt template from system_prompt.txt file

    Returns
    -------
    str
        The system prompt content
    """
    return _load_prompt_template_from_file("prompts/system_prompt.txt")


def load_prompt_template(num_few_shots: int = 0, instructions: str = "") -> tuple[str, list[str]]:
    """
    Creates prompt template by loading the base template from prompt.txt file
    and dynamically adding few-shot examples and instructions as needed.

    Parameters
    ----------
    num_few_shots : int, by default 0
        Number of few shots to be included into the prompt
    instructions : str, by default ""
        Additional document-level instructions

    Returns
    -------
    tuple[str, list[str]]
        Returns a tuple containing the prompt string and list of input variables
    """

    # Load the base prompt template from file
    base_prompt_template = _load_prompt_template_from_file("prompts/prompt.txt")

    # prepare input variables
    input_variables = ["document", "attributes"]
    for i in range(num_few_shots):
        input_variables += [f"few_shot_input_{i}", f"few_shot_output_{i}"]

    # Split the base template to insert few-shot examples before the final attributes section
    # Find the position where we should insert few-shot examples (before "Attributes to be extracted:")
    attributes_pos = base_prompt_template.find("Attributes to be extracted:")
    if attributes_pos == -1:
        raise ValueError("Invalid prompt template format: no 'Attributes to be extracted:' marker found")

    prompt_header = base_prompt_template[:attributes_pos].rstrip()
    prompt_tail = base_prompt_template[attributes_pos:]

    # prepare the prompt
    prompt = prompt_header
    for i in range(num_few_shots):
        prompt += "\n" + PROMPT_FEW_SHOT.format(
            few_shot_input_placeholder="{" + f"few_shot_input_{i}" + "}",
            few_shot_output_placeholder="{" + f"few_shot_output_{i}" + "}",
        )
    prompt += "\n" + prompt_tail

    # add instructions
    if instructions.strip():
        prompt = prompt.replace(
            "<document_level_instructions_placeholder>",
            PROMPT_INSTRUCTIONS,
        )
        input_variables.append("instructions")
    else:
        prompt = prompt.replace("\n<document_level_instructions_placeholder>\n", "\n")

    return prompt, input_variables


def fill_prompt_template(attributes: str = "", template: str = "", instructions: str = "", document: str = "") -> str:
    """
    Fills the prompt template with the provided attributes, instructions, and document content.

    Parameters
    ----------
    attributes : str, optional
        Attributes string to be inserted into the template (default: "")
    template : str, optional
        Unfilled prompt template string with placeholders (default: "")
    instructions : str, optional
        Instructions string to be inserted into the template (default: "")
    document : str, optional
        Document string to be inserted into the template (default: "")

    Returns
    -------
    str
        The filled prompt template with all placeholders replaced
    """
    return template.format(attributes=attributes, instructions=instructions, document=document)
