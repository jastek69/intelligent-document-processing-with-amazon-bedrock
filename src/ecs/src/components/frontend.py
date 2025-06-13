"""
Copyright © Amazon.com and Affiliates
"""

import components.authenticate as authenticate
import streamlit as st


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
