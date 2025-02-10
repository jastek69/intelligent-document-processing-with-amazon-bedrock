"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Prompting utils
"""

PROMPT_DEFAULT_HEADER = """You are an AI assistant who is expert in extracting information from documents.
Carefully read the document given below in <document></document> tags.
Extract attributes listed below in <attributes></attributes> tags from the document.
The answer must contain the extracted attributes in JSON format. Do NOT include any other information in the answer.
If the attribute has multiple values, provide them as a list in this format: ["value1", "value2", "value3"].
If the attribute requires providing a description or free-form text, the value of the attribute must contain this text.
Note that some attributes are not directly stated in the document, but their values are implicitly defined in the text.
Do your best to extract a full value for each requested attribute from the document.
If provided, you must also follow the additional instructions in <instructions></instructions>.
Think step by step. First, summarize your thoughts in 2-3 sentences using <thinking></thinking> tags. Next, output the JSON in <json></json> tags. Do NOT include any other information in the answer. Remember that the response MUST be a valid JSON file.

Human:
<example>
Document:
<document>
I would like to apologize for the delay in the delivery of the ordered goods. Unfortunately, there was a delay due to a technical problem in our warehouse.
Your order 754263 has now been shipped and you should receive the goods within the next 2-3 business days. I ask for your understanding regarding these inconveniences.
Kind regards,
Nikita Schulz
Customer Service ABC GmbH
</document>

Attributes to be extracted:
<attributes>
1. customer_name: name of the customer who wrote the email
2. shipment_delay_complaint: whether the email is from a customer complaining about shipment delays
3. urgency_score: how soon we should react to the customer email on a scale from 0 to 1
</attributes>

Output:
<thinking>
The document mentions the customer name in the email signature: Nikita Schulz. In the email, the customer is complaining about shipment delays. There are no data points that indicate very high urgency, so I will assign a neutral score of 0.5/
</thinking>
<json>
{{
    "customer_name": "Nikita Schulz",
    "shipment_delay_complaint": true,
    "urgency_score": 0.5,
}}
</json>
</example>
"""  # noqa: E501


PROMPT_DEFAULT_TAIL = """Document:
<document>
{document}
</document>

Attributes to be extracted:
<attributes>
{attributes}
</attributes>

<document_level_instructions_placeholder>

Output:"""


PROMPT_FEW_SHOT = """<example>
Document:
<document>
{few_shot_input_placeholder}
</document>

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


def load_prompt_template(num_few_shots: int = 0, instructions: str = "") -> tuple[str, list[str]]:
    """
    Creates prompt template

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

    # prepare input variables
    input_variables = ["document", "attributes"]
    for i in range(num_few_shots):
        input_variables += [f"few_shot_input_{i}", f"few_shot_output_{i}"]

    # prepare the prompt
    prompt = PROMPT_DEFAULT_HEADER
    for i in range(num_few_shots):
        prompt += PROMPT_FEW_SHOT.format(
            few_shot_input_placeholder="{" + f"few_shot_input_{i}" + "}",
            few_shot_output_placeholder="{" + f"few_shot_output_{i}" + "}",
        )
    prompt += PROMPT_DEFAULT_TAIL

    # add instructions
    if instructions.strip():
        prompt = prompt.replace(
            "<document_level_instructions_placeholder>",
            PROMPT_INSTRUCTIONS,
        )
        input_variables += "instructions"
    else:
        prompt = prompt.replace("\n<document_level_instructions_placeholder>\n", "\n")

    return prompt, input_variables
