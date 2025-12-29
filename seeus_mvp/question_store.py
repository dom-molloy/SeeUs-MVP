import requests
import streamlit as st

def _validate_bank(data: list[dict]):
    if not isinstance(data, list):
        raise ValueError("Question bank must be a list")

    seen = set()
    for q in data:
        if "id" not in q:
            raise ValueError("Each question must have an id")
        if q["id"] in seen:
            raise ValueError(f"Duplicate question id: {q['id']}")
        seen.add(q["id"])

@st.cache_data(show_spinner=False)
def load_question_bank(url: str) -> list[dict]:
    if not url:
        raise RuntimeError("QUESTIONS_URL is not set")

    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    _validate_bank(data)
    return data 
