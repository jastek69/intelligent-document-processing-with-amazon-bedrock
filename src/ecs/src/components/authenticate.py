"""
Copyright © Amazon.com and Affiliates
"""

import base64
import json
import logging
import os
import sys
from datetime import datetime
from typing import Union

import boto3
import jwt
import qrcode
import requests
import streamlit as st
from botocore.exceptions import ClientError, ParamValidationError
from jwt import PyJWKClient
from qrcode.image.styledpil import StyledPilImage

LOGGER = logging.Logger("ECS", level=logging.DEBUG)
HANDLER = logging.StreamHandler(sys.stdout)
HANDLER.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
LOGGER.addHandler(HANDLER)


# Initialize Cognito client
if "AWS_ACCESS_KEY_ID" in os.environ:
    print("Local Environment.")
    client = boto3.client(
        "cognito-idp",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
        region_name=os.environ.get("REGION"),
    )
else:
    client = boto3.client("cognito-idp")

# Cognito config
CLIENT_ID = os.environ["CLIENT_ID"]
USER_POOL_ID = os.environ["USER_POOL_ID"]
REGION = os.environ.get("REGION")
if not os.environ.get("LOCAL_AUTH_FLOW"):
    CLOUDFRONT_DOMAIN = os.environ["CLOUDFRONT_DOMAIN"]
COGNITO_DOMAIN = os.environ["COGNITO_DOMAIN"]
LOGOUT_URI = "http://localhost:8501" if os.environ.get("LOCAL_AUTH_FLOW") else f"https://{CLOUDFRONT_DOMAIN}"

# Initialize the JWT client
jwks_client = PyJWKClient(f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json")


def initialise_st_state_vars() -> None:
    """
    Initialise Streamlit state variables

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    st.session_state.setdefault("auth_code", "")
    st.session_state.setdefault("authenticated", "")
    st.session_state.setdefault("user_cognito_groups", "")
    st.session_state.setdefault("access_tkn", "")
    st.session_state.setdefault("refresh_tkn", "")
    st.session_state.setdefault("challenge", "")
    st.session_state.setdefault("mfa_setup_link", "")
    st.session_state.setdefault("session", "")


def generate_qrcode(url: str, path: str) -> str:
    """
    Generate QR code for MFA

    Parameters
    ----------
    url : str
        URL for the QR code
    path : str
        Folder to save generated codes

    Returns
    -------
    str
        Local path to the QR code
    """
    # create folder if needed
    if not os.path.exists(path):
        os.mkdir(path)

    # generate image
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=StyledPilImage)

    # save locally
    current_ts = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
    qrcode_path = os.path.join(path, f"qrcode_{current_ts}.png")
    img.save(qrcode_path)
    return qrcode_path


def verify_access_token(token):
    """
    Verify access token

    Parameters
    ----------
    token : str
        Access token to verify

    Returns
    -------
    bool
        True if token is valid, False otherwise
    """
    try:
        # Get the signing key
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Decode and verify the token
        decoded_data = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}",
            options={
                "verify_aud": False,
                "verify_signature": True,
                "verify_exp": False,
                "verify_iss": True,
                "require": ["token_use", "exp", "iss", "sub"],
            },
        )
        expires = decoded_data["exp"]
        now = datetime.now().timestamp()
        return (expires - now) > 0

    except jwt.exceptions.InvalidTokenError as e:
        LOGGER.error(f"Invalid token: {str(e)}")
        raise Exception("Invalid token")  # noqa: B904


def update_access_token() -> None:
    """
    Get new access token using the refresh token

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    try:
        response = client.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": st.session_state["refresh_tkn"]},
            ClientId=CLIENT_ID,
        )
        if "AuthenticationResult" in response:
            access_token = response["AuthenticationResult"]["AccessToken"]
            st.session_state["access_tkn"] = access_token
            st.session_state["authenticated"] = True
            LOGGER.info("Access token refreshed successfully.")
    except ClientError as e:
        LOGGER.error(f"Failed to refresh access token: {e.response['Error']['Message']}")
        st.session_state["authenticated"] = False
        st.session_state.pop("access_tkn", None)
        st.session_state.pop("refresh_tkn", None)


def pad_base64(data: str) -> str:
    """
    Decode access token to JWT to get user's Cognito groups

    Parameters
    ----------
    data : str
        Access token to decode

    Returns
    -------
    str
        Decoded access token
    """
    missing_padding = len(data) % 4
    if missing_padding != 0:
        data += "=" * (4 - missing_padding)
    return data


def get_user_attributes(id_tkn: str) -> dict:
    """
    Decode ID token to get user Cognito groups.

    Parameters
    ----------
    id_tkn : str
        ID token to decode

    Returns
    -------
    dict
        User attributes
    """
    user_attrib_dict = {}

    if id_tkn != "":
        _, payload, _ = id_tkn.split(".")
        printable_payload = base64.urlsafe_b64decode(pad_base64(payload))
        payload_dict = dict(json.loads(printable_payload))
        if "cognito:groups" in payload_dict:
            user_cognito_groups = list(payload_dict["cognito:groups"])
            user_attrib_dict["user_cognito_groups"] = user_cognito_groups
        if "cognito:username" in payload_dict:
            username = payload_dict["cognito:username"]
            user_attrib_dict["username"] = username
    return user_attrib_dict


def set_st_state_vars() -> None:
    """
    Set Streamlit state variables after user authentication

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    initialise_st_state_vars()

    if "access_tkn" in st.session_state and st.session_state["access_tkn"] != "":
        # If there is an access token, check if still valid
        is_valid = verify_access_token(st.session_state["access_tkn"])

        # If token not valid anymore, create a new one with refresh token
        if not is_valid:
            update_access_token()


def login_successful(response: dict) -> None:
    """
    Update Streamlit state variables on successful login

    Parameters
    ----------
    response : dict
        Response from Cognito

    Returns
    -------
    None
    """
    access_token = response["AuthenticationResult"]["AccessToken"]
    id_tkn = response["AuthenticationResult"]["IdToken"]
    refresh_token = response["AuthenticationResult"]["RefreshToken"]

    user_attributes_dict = get_user_attributes(id_tkn)

    if access_token != "":
        st.session_state["access_tkn"] = access_token
        st.session_state["refresh_tkn"] = refresh_token
        st.session_state["authenticated"] = True
        st.session_state["user_cognito_groups"] = user_attributes_dict.get("user_cognito_groups", [])
        st.session_state["user_id"] = user_attributes_dict.get("username", "")
        LOGGER.info("User successfully logged in.")


def associate_software_token(user: str, session: str) -> Union[str, None]:
    """
    Associate new MFA token to user during MFA setup

    Parameters
    ----------
    user : str
        User to associate MFA token to
    session : str
        Session to associate MFA token to

    Returns
    -------
    str | None
        Session or None if failed
    """
    try:
        response = client.associate_software_token(Session=session)
        secret_code = response["SecretCode"]
        st.session_state["mfa_setup_link"] = f"otpauth://totp/{user}?secret={secret_code}"
        return response["Session"]
    except ClientError as e:
        LOGGER.error(f"Failed to associate software token: {e.response['Error']['Message']}")
        return None


def sign_in(username: str, pwd: str) -> None:
    """
    User sign in with username and password, will store following challenge parameters in state

    Parameters
    ----------
    username : str
        Username to sign in with
    pwd : str
        Password to sign in with

    Returns
    -------
    None
    """
    try:
        response = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": pwd},
            ClientId=CLIENT_ID,
        )
    except ClientError as e:
        LOGGER.error(f"Authentication failed: {e.response['Error']['Message']}")
        st.session_state["authenticated"] = False
        st.error("Authentication failed. Please check your credentials.")
    else:
        if "ChallengeName" in response:
            st.session_state["challenge"] = response["ChallengeName"]

            if "USER_ID_FOR_SRP" in response["ChallengeParameters"]:
                st.session_state["challenge_user"] = response["ChallengeParameters"]["USER_ID_FOR_SRP"]

            if response["ChallengeName"] == "MFA_SETUP":
                session = associate_software_token(st.session_state["challenge_user"], response["Session"])
                if session:
                    st.session_state["session"] = session
            else:
                st.session_state["session"] = response["Session"]
        else:
            login_successful(response)


def verify_token(token: str) -> tuple[bool, str]:
    """
    Verify MFA token to complete MFA setup

    Parameters
    ----------
    token : str
        MFA token to verify

    Returns
    -------
    bool
        True if token is valid, False otherwise
    """
    success = False
    message = ""
    try:
        response = client.verify_software_token(
            Session=st.session_state["session"],
            UserCode=token,
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidParameterException":
            message = "Please enter 6 or more digit numbers."
        else:
            message = "Session expired, please reload the page and scan the QR code again."
    except ParamValidationError:
        message = "Please enter 6 or more digit numbers."
    else:
        if response["Status"] == "SUCCESS":
            st.session_state["session"] = response["Session"]
            success = True
    return success, message


def setup_mfa() -> tuple[bool, str]:
    """
    Reply to MFA setup challenge

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    message = ""
    success = False
    try:
        response = client.respond_to_auth_challenge(
            ClientId=CLIENT_ID,
            ChallengeName="MFA_SETUP",
            Session=st.session_state["session"],
            ChallengeResponses={
                "USERNAME": st.session_state["challenge_user"],
            },
        )
    except ClientError as e:
        LOGGER.error(f"MFA setup failed: {e.response['Error']['Message']}")
        message = "Session expired, please sign out and in again."
    else:
        success = True
        st.session_state["challenge"] = ""
        st.session_state["session"] = ""
        login_successful(response)
    return success, message


def sign_in_with_token(token: str) -> tuple[bool, str]:
    """
    Verify MFA token and complete login process

    Parameters
    ----------
    token : str
        MFA token to verify

    Returns
    -------
    None
    """
    message = ""
    success = False
    try:
        response = client.respond_to_auth_challenge(
            ClientId=CLIENT_ID,
            ChallengeName="SOFTWARE_TOKEN_MFA",
            Session=st.session_state["session"],
            ChallengeResponses={
                "USERNAME": st.session_state["challenge_user"],
                "SOFTWARE_TOKEN_MFA_CODE": token,
            },
        )
    except ClientError as e:
        LOGGER.error(f"MFA verification failed: {e.response['Error']['Message']}")
        message = "Session expired, please sign out and in again."
    else:
        success = True
        st.session_state["challenge"] = ""
        st.session_state["session"] = ""
        login_successful(response)
    return success, message


def reset_password(password: str) -> tuple[bool, str]:
    """
    Reset password on first connection, will store parameters of following challenge

    Parameters
    ----------
    password : str
        Password to reset

    Returns
    -------
    None
    """
    message = ""
    success = False
    try:
        response = client.respond_to_auth_challenge(
            ClientId=CLIENT_ID,
            ChallengeName="NEW_PASSWORD_REQUIRED",
            Session=st.session_state["session"],
            ChallengeResponses={
                "NEW_PASSWORD": password,
                "USERNAME": st.session_state["challenge_user"],
            },
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidPasswordException":
            message = e.response["Error"]["Message"]
        else:
            message = "Session expired, please sign out and in again."
    else:
        success = True
        if "ChallengeName" in response:
            st.session_state["challenge"] = response["ChallengeName"]
            if response["ChallengeName"] == "MFA_SETUP":
                session = associate_software_token(st.session_state["challenge_user"], response["Session"])
                if session:
                    st.session_state["session"] = session
            else:
                st.session_state["session"] = response["Session"]
        else:
            st.session_state["challenge"] = ""
            st.session_state["session"] = ""
    return success, message


def sign_out() -> None:
    """
    Sign out user by updating all relevant state parameters

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    if st.session_state.get("refresh_tkn"):
        try:
            response = requests.post(
                f"https://{COGNITO_DOMAIN}/oauth2/revoke",
                data={
                    "token": st.session_state["refresh_tkn"],
                    "client_id": CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=60,
            )
            if response.status_code != 200:
                LOGGER.error(f"Failed to revoke token: {response.text}")
        except Exception as e:
            LOGGER.error(f"Exception during token revocation: {str(e)}")

    st.session_state["authenticated"] = False
    st.session_state["user_cognito_groups"] = []
    st.session_state["access_tkn"] = ""
    st.session_state["refresh_tkn"] = ""
    st.session_state["challenge"] = ""
    st.session_state["session"] = ""

    # Construct the logout URL with the logout_uri parameter
    COGNITO_LOGOUT_URL = f"https://{COGNITO_DOMAIN}/logout?client_id={CLIENT_ID}&logout_uri={LOGOUT_URI}"
    LOGGER.debug(f"Redirecting to Cognito Logout URL: {COGNITO_LOGOUT_URL}")
    # Redirect the user to the Cognito logout page
    st.markdown(f'<meta http-equiv="refresh" content="0; url={COGNITO_LOGOUT_URL}" />', unsafe_allow_html=True)
    st.stop()


def local_redirect_to_cognito() -> None:
    """
    For local dev: If there's no ?code=... in the root URL, redirect to Cognito's authorize endpoint.
    The callback is now just http://localhost:8501, not /oauth2/idpresponse.

    Parameters
    ----------
    None

    Returns
    -------
    None
    """
    query_params = st.query_params
    if "code" not in query_params:
        cognito_domain = os.environ.get("COGNITO_DOMAIN")  # e.g. "my-user-pool.auth.us-west-2.amazoncognito.com"
        client_id = os.environ.get("CLIENT_ID")
        if cognito_domain and client_id:
            # We'll redirect back to root
            redirect_uri = "http://localhost:8501"
            authorize_url = (
                f"https://{cognito_domain}/oauth2/authorize"
                f"?client_id={client_id}"
                f"&response_type=code"
                f"&scope=openid+profile+email"
                f"&redirect_uri={redirect_uri}"
            )
            st.write("Redirecting to Cognito for local sign-in...")
            st.markdown(f'<meta http-equiv="refresh" content="0; url={authorize_url}" />', unsafe_allow_html=True)
            st.stop()
        else:
            st.error("No Cognito config found for local login. Set COGNITO_DOMAIN, CLIENT_ID, etc.")
            st.stop()


def exchange_code_for_token(code: str, token_endpoint: str, prod_direct_uri: str) -> dict:
    """
    Exchanges the code for an access token.
    For local dev, we assume redirect_uri=http://localhost:8501
    For production, we do https://{CLOUDFRONT_DOMAIN}/oauth2/idpresponse

    Parameters
    ----------
    code : str
        Code to exchange for token
    token_endpoint : str
        Token endpoint to exchange code for token
    prod_direct_uri : str
        Production direct URI

    Returns
    -------
    dict
        Token
    """
    LOGGER.info("Exchanging code for token...")

    # Decide redirect URI based on local_auth_flow
    redirect_uri = "http://localhost:8501" if st.session_state["local_auth_flow"] else prod_direct_uri

    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        LOGGER.debug(f"Requesting token from {token_endpoint}")
        resp = requests.post(token_endpoint, data=data, headers=headers, timeout=60)
        resp.raise_for_status()
        LOGGER.debug(f"Response status: {resp.status_code}, resp headers: {resp.headers}")
        if resp.status_code == 200:
            return resp.json()
        LOGGER.error(f"Token exchange failed: {resp.text}")
    except Exception as e:
        LOGGER.error(f"Exception during token exchange: {e}")
    return {}
