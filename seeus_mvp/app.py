# Optional: load .env locally. Safe on Streamlit Cloud even if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import os
import json
import uuid
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode

# -------------------------------------------------------------------
# 🔑 CRITICAL: Ensure local modules are importable on Streamlit Cloud
# -------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st

from growth_ui import render_growth_dashboard
from question_store import load_question_bank

from db import (
    save_report, get_latest_report,
    init_db, upsert_user, create_relationship, list_relationships, get_relationship,
    create_session, get_open_session, end_session, save_response,
    get_answers_for_session, get_last_answers, get_answer_history,
    create_invite, get_invite, mark_invite_used,
    archive_relationship, restore_relationship,
)

# 🐞 Bug tracker (LOCAL import — REQUIRED)
from bugs import (
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


# -------------------- CONFIG --------------------
st.set_page_config(page_title="SeeUs MVP", layout="centered")
init_db()

BASE_APP_URL = (os.getenv("BASE_APP_URL") or "").strip() or \
    "https://seeus-mvp-nfbw9pe3pclpgw4kchx9gh.streamlit.app"

DEFAULT_QUESTIONS_URL = (
    "https://raw.githubusercontent.com/dom-molloy/SeeUs-Question-Bank/main/questions_bank.json"
)


# -------------------- HELPERS --------------------
def _get_setting(key: str, default: str = "") -> str:
    try:
        return str(st.secrets[key])
    except Exception:
        return str(os.getenv(key, default) or default)


def _get_query_param(name: str):
    try:
        v = st.query_params.get(name)
        if isinstance(v, (list, tuple)):
            return v[0] if v else None
        return v
    except Exception:
        pass
    try:
        qp = st.experimental_get_query_params()
        v = qp.get(name, [None])
        return v[0] if isinstance(v, list) else v
    except Exception:
        return None


def latest_map(rows_desc):
    m = {}
    for r in reversed(rows_desc):
        m[r["question_id"]] = r["answer_text"]
    return m


def _is_archived_row(r) -> bool:
    try:
        return int(r["is_archived"] or 0) == 1
    except Exception:
        return False


# -------------------- BUG TRACKER --------------------
def render_bug_tracker(current_user: str):
    st.header("🐞 Bug Tracker")

    m = bug_metrics()
    c1, c2, c3 = st.columns(3)
    c1.metric("Open Critical", m["open_critical"])
    c2.metric("Total Bugs", sum(m["by_status"].values()) if m["by_status"] else 0)
    c3.metric("Closed", m["by_status"].get("Closed", 0))

    st.divider()

    with st.expander("Report a bug"):
        with st.form("bug_create"):
            title = st.text_input("Title")
            desc = st.text_area("Description")
            sev = st.selectbox("Severity", SEVERITIES, index=1)
            if st.form_submit_button("Submit"):
                if not title or not desc:
                    st.error("Title and description required.")
                else:
                    create_bug(title, desc, current_user, sev)
                    st.success("Bug submitted.")
                    st.rerun()

    st.divider()

    status = st.selectbox("Status", ["All"] + BUG_STATUSES)
    bugs = list_bugs(status=status)

    if not bugs:
        st.info("No bugs.")
        return

    labels = {f"[{b['status']}] {b['title']}": b["id"] for b in bugs}
    choice = st.selectbox("Select bug", list(labels))
    bug = get_bug(labels[choice])

    st.write("### Details")
    st.write(bug["description"])

    with st.form("bug_update"):
        new_status = st.selectbox("Status", BUG_STATUSES,
                                  index=BUG_STATUSES.index(bug["status"]))
        assignee = st.text_input("Assignee", bug["assignee"] or "")
        notes = st.text_area("Resolution Notes", bug["resolution_notes"] or "")
        if st.form_submit_button("Save"):
            update_bug(
                bug["id"],
                status=new_status,
                assignee=assignee,
                resolution_notes=notes,
            )
            st.success("Updated.")
            st.rerun()


# -------------------- INVITE LOCKING --------------------
token = _get_query_param("t")
invite = get_invite(token) if token else None

# 🚨 IMPORTANT: invalid or expired invite
if token and not invite:
    st.error("This invite link is invalid or expired (token not found).")
    st.stop()

forced_rid = invite["relationship_id"] if invite else None
forced_respondent = invite["respondent"] if invite else None

# -------------------- QUESTIONS --------------------
REMOTE_QUESTIONS_URL = _get_setting("QUESTIONS_URL") or DEFAULT_QUESTIONS_URL
QUESTIONS = load_question_bank(REMOTE_QUESTIONS_URL)
QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}
PRIMARY_IDS = [q["id"] for q in QUESTIONS if q.get("is_primary")]


# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.header("SeeUs")
    page = st.radio(
        "Go to",
        ["Assess", "Report", "Growth", "Bug Tracker", "Help"],
        index=0
    )

    st.divider()
    user_id = st.text_input("User ID", value=st.session_state.get("user_id", "pete"))
    display_name = st.text_input(
        "Display Name",
        value=st.session_state.get("display_name", "Pete")
    )
    if st.button("Save Profile"):
        st.session_state["user_id"] = user_id
        st.session_state["display_name"] = display_name
        upsert_user(user_id, display_name)
        st.success("Saved")


# -------------------- HEADER --------------------
st.title("SeeUs — Relationship Mirror")


# -------------------- ROUTING --------------------
if page == "Bug Tracker":
    render_bug_tracker(
        st.session_state.get("display_name")
        or st.session_state.get("user_id")
        or "unknown"
    )
    st.stop()

if page == "Help":
    st.markdown("Help page coming soon.")
    st.stop()

if page == "Growth":
    rid = st.session_state.get("relationship_id")
    if rid:
        render_growth_dashboard(rid, "solo", "solo")
    st.stop()

# -------------------- ASSESS (default) --------------------
st.markdown("Assessment UI continues here…")
