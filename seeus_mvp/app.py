# seeus_mvp/app.py

# Optional: load .env locally. Safe on Streamlit Cloud even if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import os
import json  # ✅ FIX: was jsona
import uuid
from datetime import datetime
from urllib.parse import urlencode

import streamlit as st

from question_store import load_question_bank

from db import (
    save_report, get_latest_report,
    init_db, upsert_user, create_relationship, list_relationships, get_relationship,
    create_session, get_open_session, end_session, save_response,
    get_answers_for_session, get_last_answers, get_answer_history,
    create_invite, get_invite, mark_invite_used,
    archive_relationship, restore_relationship,
)

from bugs import (
    init_bugs_table,
    create_bug, list_bugs, get_bug, update_bug,
    BUG_STATUSES, SEVERITIES, bug_metrics
)

from scoring import score_solo, score_duo, overall_score
from llm_scoring import score_duo_llm, overall_from_llm
from reporting import DIMENSION_ORDER, DIMENSION_LABELS, build_headlines
from deep_research import run_deep_research
from research_packet import build_key_quotes, detect_contradictions, compute_deltas_over_time
from render_brief import render_brief
from pdf_export import brief_to_pdf_bytes
from growth_ui import render_growth_dashboard


# -------------------- CONFIG --------------------
st.set_page_config(page_title="SeeUs MVP", layout="centered")


# ✅ FIX: make DB/table init safe + non-blocking on reruns
@st.cache_resource
def _bootstrap():
    # If anything fails here, we WANT to see it in the app
    init_db()
    init_bugs_table()
    return True


try:
    _bootstrap()
except Exception as e:
    st.error("Startup failed during database initialization.")
    st.exception(e)
    st.stop()


BASE_APP_URL = (os.getenv("BASE_APP_URL") or "").strip() or "https://seeus-mvp-nfbw9pe3pclpgw4kchx9gh.streamlit.app"
DEFAULT_QUESTIONS_URL = "https://raw.githubusercontent.com/dom-molloy/SeeUs-Question-Bank/main/questions_bank.json"
