"""
Utilities for Cognito authentication
"""

import base64
import json
import os
from datetime import datetime

import boto3
import jwt
import qrcode
import streamlit as st
from botocore.exceptions import ClientError, ParamValidationError
from jwt import PyJWKClient
from qrcode.image.styledpil import StyledPilImage

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

# constants
CLIENT_ID = os.environ.get("CLIENT_ID")
USER_POOL_ID = os.environ.get("USER_POOL_ID")
REGION = os.environ.get("REGION")

# Initialize the JWT client
jwks_client = PyJWKClient(f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json")


def initialise_st_state_vars() -> None:
    """
    Initialise Streamlit state variables
    """
    st.session_state.setdefault("auth_code", "")
    st.session_state.setdefault("authenticated", "")
    st.session_state.setdefault("user_cognito_groups", "")
    st.session_state.setdefault("access_tkn", "")
    st.session_state.setdefault("refresh_tkn", "")
    st.session_state.setdefault("challenge", "")
    st.session_state.setdefault("mfa_setup_link", "")


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
    qrcode_path = path + "qrcode_" + str(current_ts) + ".png"
    img.save(qrcode_path)
    return qrcode_path


def verify_access_token(token):
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

    except jwt.exceptions.InvalidTokenError:
        raise Exception("Invalid token")


def update_access_token() -> None:
    """
    Get new access token using the refresh token
    """
    try:
        response = client.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": st.session_state["refresh_tkn"]},
            ClientId=os.environ.get("CLIENT_ID"),
        )

    except ClientError:
        st.session_state["authenticated"] = False
        st.session_state["access_tkn"] = ""
        st.session_state["user_cognito_groups"] = []
        st.session_state["refresh_tkn"] = ""
    else:
        access_token = response["AuthenticationResult"]["AccessToken"]
        id_tkn = response["AuthenticationResult"]["IdToken"]
        user_attributes_dict = get_user_attributes(id_tkn)
        st.session_state["access_tkn"] = access_token
        st.session_state["authenticated"] = True
        st.session_state["user_cognito_groups"] = None
        if "user_cognito_groups" in user_attributes_dict:
            st.session_state["user_cognito_groups"] = user_attributes_dict["user_cognito_groups"]
        st.session_state["user_id"] = ""
        if "username" in user_attributes_dict:
            st.session_state["user_id"] = user_attributes_dict["username"]


def pad_base64(data: str) -> str:
    """
    Decode access token to JWT to get user's cognito groups
    Ref - https://gist.github.com/GuillaumeDerval/b300af6d4f906f38a051351afab3b95c

    Parameters
    ----------
    data : str
        base64 token string

    Returns
    -------
    str
        padded token string
    """

    missing_padding = len(data) % 4
    if missing_padding != 0:
        data += "=" * (4 - missing_padding)
    return data


def get_user_attributes(id_tkn: str) -> dict:
    """
    Decode id token to get user cognito groups.

    Parameters
    ----------
    id_tkn : str
        ID token of a successfully authenticated user

    Returns
    -------
    dict
        Dictionary with two keys (username, and list of all the cognito groups the user belongs to)
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
    Sets the streamlit state variables after user authentication.
    """

    initialise_st_state_vars()

    if "access_tkn" in st.session_state and st.session_state["access_tkn"] != "":
        # If there is an access token, check if still valid
        is_valid = verify_access_token(st.session_state["access_tkn"])

        # If token not valid anymore create a new one with refresh token
        if not is_valid:
            update_access_token()


def login_successful(response: dict) -> None:
    """
    Update streamlit state variables on successful login

    Parameters
    ----------
    response : dict
        boto3 response of the successful login API call
    """

    access_token = response["AuthenticationResult"]["AccessToken"]
    id_tkn = response["AuthenticationResult"]["IdToken"]
    refresh_token = response["AuthenticationResult"]["RefreshToken"]

    user_attributes_dict = get_user_attributes(id_tkn)

    if access_token != "":
        st.session_state["access_tkn"] = access_token
        st.session_state["authenticated"] = True
        st.session_state["user_cognito_groups"] = None
        if "user_cognito_groups" in user_attributes_dict:
            st.session_state["user_cognito_groups"] = user_attributes_dict["user_cognito_groups"]
        st.session_state["user_id"] = ""
        if "username" in user_attributes_dict:
            st.session_state["user_id"] = user_attributes_dict["username"]
        st.session_state["refresh_tkn"] = refresh_token


def associate_software_token(user, session):
    """
    Associate new MFA token to user during MFA setup

    Parameters
    ----------
    user : _type_
        the user from MFA_SETUP challenge
    session : _type_
        valid user session

    Returns
    -------
    _type_
        New valid user session
    """

    response = client.associate_software_token(Session=session)

    secret_code = response["SecretCode"]
    st.session_state["mfa_setup_link"] = f"otpauth://totp/{user}?secret={secret_code}"

    return response["Session"]


def sign_in(username: str, pwd: str) -> None:
    """
    User sign in with user name and password, will store following challenge parameters in state

    Parameters
    ----------
    username : str
        user provided username
    pwd : str
        user provided password
    """

    try:
        response = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": username, "PASSWORD": pwd},
            ClientId=os.environ.get("CLIENT_ID"),
        )

    except ClientError:
        st.session_state["authenticated"] = False

    else:
        if "ChallengeName" in response:
            st.session_state["challenge"] = response["ChallengeName"]

            if "USER_ID_FOR_SRP" in response["ChallengeParameters"]:
                st.session_state["challenge_user"] = response["ChallengeParameters"]["USER_ID_FOR_SRP"]

            if response["ChallengeName"] == "MFA_SETUP":
                session = associate_software_token(st.session_state["challenge_user"], response["Session"])
                st.session_state["session"] = session
            else:
                st.session_state["session"] = response["Session"]

        else:
            login_successful(response)


def verify_token(token: str):
    """
    Verify MFA token to complete MFA setup

    Parameters
    ----------
    token : str
        token from user MFA app

    Returns
    -------
    _type_
        success : bool
            True if succeeded, False otherwise
        message : str
            Error message
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


def setup_mfa():
    """
    Reply to MFA setup challenge
    The current session has to be updated by verify token function

    Returns
    -------
    _type_
        success : bool
            True if succeeded, False otherwise
        message : str
            Error message
    """

    message = ""
    success = False

    try:
        response = client.respond_to_auth_challenge(
            ClientId=os.environ.get("CLIENT_ID"),
            ChallengeName="MFA_SETUP",
            Session=st.session_state["session"],
            ChallengeResponses={
                "USERNAME": st.session_state["challenge_user"],
            },
        )

    except ClientError:
        message = "Session expired, please sign out and in again."
    else:
        success = True
        st.session_state["challenge"] = ""
        st.session_state["session"] = ""
        login_successful(response)

    return success, message


def sign_in_with_token(token: str):
    """
    Verify MFA token and complete login process

    Parameters
    ----------
    token : str
        token from user MFA app

    Returns
    -------
    _type_
        success : bool
            True if succeeded, False otherwise
        message : str
            Error message
    """

    message = ""
    success = False
    try:
        response = client.respond_to_auth_challenge(
            ClientId=os.environ.get("CLIENT_ID"),
            ChallengeName="SOFTWARE_TOKEN_MFA",
            Session=st.session_state["session"],
            ChallengeResponses={
                "USERNAME": st.session_state["challenge_user"],
                "SOFTWARE_TOKEN_MFA_CODE": token,
            },
        )

    except ClientError:
        message = "Session expired, please sign out and in again."
    else:
        success = True
        st.session_state["challenge"] = ""
        st.session_state["session"] = ""
        login_successful(response)

    return success, message


def reset_password(password: str):
    """
    Reset password on first connection, will store parameters of following challenge

    Parameters
    ----------
    password : str
        new password to set

    Returns
    -------
    _type_
        success : bool
            True if succeeded, False otherwise
        message : str
            Error message
    """

    message = ""
    success = False

    try:
        response = client.respond_to_auth_challenge(
            ClientId=os.environ.get("CLIENT_ID"),
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
    """
    if st.session_state["refresh_tkn"] != "":
        client.revoke_token(
            Token=st.session_state["refresh_tkn"],
            ClientId=os.environ.get("CLIENT_ID"),
        )

    st.session_state["authenticated"] = False
    st.session_state["user_cognito_groups"] = []
    st.session_state["access_tkn"] = ""
    st.session_state["refresh_tkn"] = ""
    st.session_state["challenge"] = ""
    st.session_state["session"] = ""
