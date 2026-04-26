import streamlit as st
from streamlit_authenticator import Authenticate, Hasher

credentials_data = {
    "usernames": {
        "admin": {
            "name": "Administrator",
            "password": "admin123",
        }
    }
}

authenticator = Authenticate(
    credentials_data,
    "furniture_showroom_cookie",
    "furniture_showroom_signature",
    cookie_expiry_days=1,
    auto_hash=True,
)


def login():
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

    if submit:
        if username in credentials_data["usernames"]:
            hashed_pw = credentials_data["usernames"][username]["password"]
            if Hasher().check_pw(password, hashed_pw):
                st.session_state["authentication_status"] = True
                st.session_state["name"] = credentials_data["usernames"][username]["name"]
                st.session_state["username"] = username
                st.success(f"Welcome {credentials_data['usernames'][username]['name']}!")
                return True
            else:
                st.error("Invalid username or password")
                return False
        else:
            st.error("Invalid username or password")
            return False
    return None


def logout():
    authenticator.logout("Logout", "sidebar")


def require_authentication() -> bool:
    return bool(st.session_state.get("authentication_status"))


def get_current_user():
    return st.session_state.get("name")
