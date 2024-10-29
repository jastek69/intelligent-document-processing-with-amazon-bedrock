"""
Copyright © Amazon.com and Affiliates
----------------------------------------------------------------------
File content:
    Streamlit Frontend
"""

#########################
#    IMPORTS & LOGGER
#########################

import logging
import os
import sys

import streamlit as st
from components.ssm import load_ssm_params
from dotenv import dotenv_values, load_dotenv
from PIL import Image

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

import components.authenticate as authenticate
from components.constants import GENERATED_QRCODES_PATH
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
COVER_IMAGE = os.environ.get("COVER_IMAGE_URL")
ASSISTANT_AVATAR = os.environ.get("ASSISTANT_AVATAR_URL")
PAGE_TITLE = "IDP Bedrock"
PAGE_ICON = ":sparkles:"

# page config
st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="centered",
    initial_sidebar_state="collapsed",
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
#    HELPER FUNCTIONS
#########################


def run_login() -> None:
    """
    Perform login
    """
    LOGGER.info("Inside run_login()")

    # authenticate
    if (st.session_state["username"] != "") & (st.session_state["password"] != ""):
        authenticate.sign_in(st.session_state["username"], st.session_state["password"])

        # check authentication
        if not st.session_state["authenticated"] and st.session_state["challenge"] not in [
            "NEW_PASSWORD_REQUIRED",
            "MFA_SETUP",
            "SOFTWARE_TOKEN_MFA",
        ]:
            st.session_state["error_message"] = "Username or password are wrong. Please try again."
        else:
            st.session_state.pop("error_message", None)

    # ask to enter credentials
    else:
        st.session_state["error_message"] = "Please enter a username and a password first."

    LOGGER.info(f"Authentication status: {st.session_state['authenticated']}")


def reset_password() -> None:
    """
    Reset password
    """
    LOGGER.info("Inside reset_password()")

    if st.session_state["challenge"] == "NEW_PASSWORD_REQUIRED":
        if (st.session_state["new_password"] != "") & (st.session_state["new_password_repeat"] != ""):
            if st.session_state["new_password"] == st.session_state["new_password_repeat"]:
                reset_success, message = authenticate.reset_password(st.session_state["new_password"])
                if not reset_success:
                    st.session_state["error_message"] = message
                else:
                    st.session_state.pop("error_message", None)
            else:
                st.session_state["error_message"] = "Entered passwords do not match."
        else:
            st.session_state["error_message"] = "Please enter a new password first."


def setup_mfa() -> None:
    """
    Setup MFA
    """
    LOGGER.info("Inside setup_mfa()")

    if st.session_state["challenge"] == "MFA_SETUP":
        if st.session_state["mfa_verify_tkn"] != "":
            token_valid, message = authenticate.verify_token(st.session_state["mfa_verify_tkn"])
            if token_valid:
                mfa_setup_success, message = authenticate.setup_mfa()
                if not mfa_setup_success:
                    st.session_state["error_message"] = message
                else:
                    st.session_state.pop("error_message", None)
            else:
                st.session_state["error_message"] = message
        else:
            st.session_state["error_message"] = "Please enter a code from your MFA app first."


def sign_in_with_token() -> None:
    """
    Verify MFA Code
    """
    LOGGER.info("Inside sign_in_with_token()")

    if st.session_state["challenge"] == "SOFTWARE_TOKEN_MFA":
        if st.session_state["mfa_tkn"] != "":
            success, message = authenticate.sign_in_with_token(st.session_state["mfa_tkn"])
            if not success:
                st.session_state["error_message"] = message
            else:
                st.session_state.pop("error_message", None)
        else:
            st.session_state["error_message"] = "Please enter a code from your MFA App first."


#########################
#       MAIN PAGE
#########################

if st.session_state["authenticated"]:
    st.switch_page("app_pages/idp_bedrock.py")

# page if password needs to be reset
if st.session_state["challenge"] == "NEW_PASSWORD_REQUIRED":
    st.warning("Please reset your password to use the app.")
    with st.form("password_reset_form"):
        new_password = st.text_input(
            key="new_password",
            placeholder="Enter your new password here",
            label="New Password",
            type="password",
        )
        new_password_repeat = st.text_input(
            key="new_password_repeat",
            placeholder="Please repeat the new password",
            label="Repeat New Password",
            type="password",
        )
        reset_button = st.form_submit_button(":recycle: Reset Password", on_click=reset_password)

# page if user need to setup MFA
elif st.session_state["challenge"] == "MFA_SETUP":
    st.warning("Scan the QR code with an MFA application such as [Authy](https://authy.com/) to access the app.")

    # generate QR code
    with st.spinner("Generating QR Code..."):
        qrcode_path = authenticate.generate_qrcode(
            url=str(st.session_state["mfa_setup_link"]), path=GENERATED_QRCODES_PATH
        )

    # display QR code
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write(" ")
    with col2:
        image = Image.open(qrcode_path)
        st.image(image, caption="MFA Setup QR Code")
    with col3:
        st.write(" ")

    # token input field
    with st.form("mfa_submit_form"):
        setup_mfa_token = st.text_input(
            key="mfa_verify_tkn",
            placeholder="Enter the verification code here",
            label="Verification Code",
        )

        # submit button
        mfa_setup_button = st.form_submit_button("Verify Token", on_click=setup_mfa)

# page if user needs to enter MFA token
elif st.session_state["challenge"] == "SOFTWARE_TOKEN_MFA":
    st.warning("Please provide a token from your MFA application.")

    # token input field
    with st.form("password_reset_form"):
        setup_mfa_token = st.text_input(
            key="mfa_tkn",
            placeholder="Enter the verification code here",
            label="Verification Token",
        )

        # verification button
        mfa_submit_button = st.form_submit_button("Verify Token", on_click=sign_in_with_token)

# page if user is logged out
else:
    st.warning("You are logged out, please log in.")
    with st.form("text_input_form"):
        username = st.text_input(
            key="username",
            placeholder="Enter your username here",
            label="Username",
        )
        password = st.text_input(
            key="password",
            placeholder="Enter your password here",
            label="Password",
            type="password",
        )
        login_button = st.form_submit_button(":bust_in_silhouette: Login", on_click=run_login)

# show error message
if "error_message" in st.session_state:
    st.error(st.session_state["error_message"])
    del st.session_state["error_message"]
