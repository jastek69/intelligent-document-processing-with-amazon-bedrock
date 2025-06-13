"""
Copyright © Amazon.com and Affiliates
"""

import streamlit as st


def set_page_styling(
    max_page_width: int = 1000, max_expander_height: int = 500, ai_message_bubble_color: str = "rgba(180,200,250,0.15)"
) -> None:
    """
    Set page layout for Streamlit UI using CSS code

    Parameters
    ----------
    max_page_width : int
        Maximum page width (in pixels), by default 800
    max_expander_height : int
        Maximum expander height (in pixels), by default 800
    ai_message_bubble_color : str
        Color of the chatbot message bubble, by default "rgba(180,200,250,0.15)"
    """

    # default template
    css_code = """<style>
section.main > div {max-width:800px}
[data-testid="stExpander"] div:has(>.streamlit-expanderContent) {
        overflow: scroll;
        max-height: 500px;
    }
[data-testid="stForm"] {border: 0px; margin:0px; padding:0px; display:inline;}
.st-emotion-cache-1c7y2kd {
    text-align: right;
    width: 60%;
    margin-left: 40%;
    text-align: justify;
}
.st-emotion-cache-4oy321 {
    text-align: left;
    max-width: 100%;
    margin-right: 0%;
    padding-right: 5%;
    width=max-content;
    text-align: justify;
    background-color: rgba(180,200,250,0.15);
}
</style>
"""

    # update param values
    css_code = css_code.replace("max-width:800px", f"max-width:{max_page_width}px")
    css_code = css_code.replace("max-height: 500px;", f"max-height: {max_expander_height}px;")
    css_code = css_code.replace("rgba(180,200,250,0.15);", f"{ai_message_bubble_color};")

    # apply styling
    st.session_state["css_code"] = css_code
    st.markdown(st.session_state["css_code"], unsafe_allow_html=True)
