"""
Copyright © Amazon.com and Affiliates
"""

import logging
import os
import sys

import streamlit as st
from components.ssm import load_ssm_params
from dotenv import dotenv_values, load_dotenv
from components.styling import set_page_styling
from st_pages import add_indentation, show_pages_from_config

# For local testing only
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

LOGGER = logging.Logger("ECS", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)

#########################
#     COVER & CONFIG
#########################

COVER_IMAGE = os.environ.get("COVER_IMAGE_URL")
ASSISTANT_AVATAR = os.environ.get("ASSISTANT_AVATAR_URL")
PAGE_TITLE = "IDP Bedrock"
PAGE_ICON = ":sparkles:"


# Cognito config
CLIENT_ID = os.environ["CLIENT_ID"]
USER_POOL_ID = os.environ["USER_POOL_ID"]
REGION = os.environ["REGION"]
CLOUDFRONT_DOMAIN = os.environ.get("CLOUDFRONT_DOMAIN")
COGNITO_DOMAIN = os.environ["COGNITO_DOMAIN"]
from components.authenticate import local_redirect_to_cognito, exchange_code_for_token  # noqa: E402


# By default, we define the production CloudFront redirect
PROD_REDIRECT_URI = f"https://{CLOUDFRONT_DOMAIN}/oauth2/idpresponse"
AUTHORIZATION_ENDPOINT = f"https://{COGNITO_DOMAIN}/oauth2/authorize"
TOKEN_ENDPOINT = f"https://{COGNITO_DOMAIN}/oauth2/token"


def init_session_state():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if "access_token" not in st.session_state:
        st.session_state["access_tkn"] = None
    if "local_auth_flow" not in st.session_state:
        # check environment variable, default to false if not set
        st.session_state["local_auth_flow"] = os.environ.get("LOCAL_AUTH_FLOW", "false").lower() == "true"


def main():
    # 1) Initialize session state
    init_session_state()

    # 2) Page config and styling
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    with st.empty():
        set_page_styling()

    LOGGER.debug("=== Starting Authentication Flow ===")
    LOGGER.debug(f"Session State: {st.session_state}")

    # 3) If local_auth_flow is True, do the local redirect logic
    if st.session_state["local_auth_flow"]:
        local_redirect_to_cognito()

    # 4) Handle code from query params
    query_params = st.query_params
    auth_code = query_params.get("code")

    LOGGER.debug(f"COGNITO_DOMAIN: {COGNITO_DOMAIN}")
    LOGGER.debug(f"TOKEN_ENDPOINT: {TOKEN_ENDPOINT}")
    LOGGER.debug(f"Current URL params: {query_params}")
    LOGGER.debug(f"Session state: {st.session_state}")

    if auth_code and not st.session_state["authenticated"]:
        LOGGER.info("Processing authentication code...")
        tokens = exchange_code_for_token(auth_code, TOKEN_ENDPOINT, PROD_REDIRECT_URI)

        if tokens:
            LOGGER.info("Authentication successful!")
            st.session_state["access_tkn"] = tokens["access_token"]
            st.session_state["authenticated"] = True
            # Clear the code from URL
            st.query_params.clear()
            # st.rerun()
        else:
            LOGGER.error("Authentication failed!")
            st.error("Failed to authenticate. Please try again.")
            st.session_state["authenticated"] = False
            st.session_state.pop("access_tkn", None)
            st.stop()

    # 5) If user is authenticated, show main content; else show "Authenticating..."
    if st.session_state["authenticated"]:
        LOGGER.info("User is authenticated, showing main content")
        # Display cover image
        LOGGER.debug(f"COVER_IMAGE URL: {COVER_IMAGE}")  # Add this debug line

        with st.container():
            if COVER_IMAGE:
                st.markdown(
                    f'<img src="{COVER_IMAGE}" width="100%" style="margin-left: auto; margin-right: auto; display: block;">',  # noqa: E501
                    unsafe_allow_html=True,
                )
                LOGGER.debug("Cover image markdown rendered")
            else:
                LOGGER.warning("COVER_IMAGE_URL environment variable is not set or is empty")
                st.warning("Cover image not available")

        # Add sidebar navigation
        add_indentation()
        show_pages_from_config()

        # Switch to main page (IDP Bedrock UI)
        st.switch_page("app_pages/idp_bedrock.py")
    else:
        LOGGER.info("User is not authenticated, showing loading state")
        st.write("Authenticating...")
        st.stop()


if __name__ == "__main__":
    main()
