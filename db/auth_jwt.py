import streamlit as st

def login_user(user_dict):
    st.session_state["user"] = user_dict

def logout():
    if "user" in st.session_state:
        del st.session_state["user"]

def is_authenticated():
    return "user" in st.session_state

def get_current_user():
    return st.session_state.get("user", None)
