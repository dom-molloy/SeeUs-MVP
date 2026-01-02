# seeus_mvp/app.py

# Optional: load .env locally. Safe on Streamlit Cloud even if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import os
import json
import uuid
import streamlit as st
from datetime import datetime
from urllib.parse import urlencode

from question_store import load_question_bank

from db import (
    save_report, get_latest_report,
    init_db, upsert_user, create_relationship, list_relationships, get_relationship,
    create_session, get_open_session, end_session, save_response,
    get_answers_for_session, get_last_answers, get_answer_history,
    create_invite, get_invite, mark_invite_used,
    archive_relationship, restore_relationship,
)

# 🐞 FIX: include init_bugs_table here
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

init_db()
# 🐞 FIX: ensure bugs table exists
init_bugs_table()

BASE_APP_URL = (os.getenv("BASE_APP_URL") or "").strip() or "https://seeus-mvp-nfbw9pe3pclpgw4kchx9gh.streamlit.app"
DEFAULT_QUESTIONS_URL = "https://raw.githubusercontent.com/dom-molloy/SeeUs-Question-Bank/main/questions_bank.json"


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
    for r in reversed(rows_desc):  # newest overwrites
        m[r["question_id"]] = r["answer_text"]
    return m


# -------------------- BUG TRACKER UI --------------------
def render_bug_tracker(current_user: str):
    st.header("🐞 Bug Tracker")

    m = bug_metrics()
    c1, c2, c3 = st.columns(3)
    c1.metric("Open Critical", m["open_critical"])
    c2.metric("Total", sum(m["by_status"].values()) if m["by_status"] else 0)
    c3.metric("Closed", m["by_status"].get("Completed", 0) + m["by_status"].get("Rejected", 0))

    st.divider()

    with st.expander("Report a bug / enhancement"):
        with st.form("bug_create_form"):
            title = st.text_input("Title", key="bug_title")
            desc = st.text_area("Description", key="bug_desc")
            sev = st.selectbox("Severity", SEVERITIES, index=1, key="bug_sev")
            if st.form_submit_button("Submit"):
                if not title.strip() or not desc.strip():
                    st.error("Title and description required.")
                else:
                    # 🐞 FIX: use desc (not description)
                    create_bug(title, desc, current_user, sev)
                    st.success("Submitted.")
                    st.rerun()

    st.divider()

    f1, f2 = st.columns(2)
    with f1:
        status = st.selectbox("Filter by status", ["All"] + BUG_STATUSES, key="bug_filter_status")
    with f2:
        sev = st.selectbox("Filter by severity", ["All"] + SEVERITIES, key="bug_filter_sev")

    bugs = list_bugs(status=status, severity=sev)
    if not bugs:
        st.info("No items match your filters.")
        return

    labels = {f"[{b['status']}] ({b['severity']}) {b['title']}": b["bug_id"] for b in bugs}
    choice = st.selectbox("Select", list(labels.keys()), key="bug_select")
    bug = get_bug(labels[choice])
    if not bug:
        st.error("Bug not found.")
        return

    st.write("### Details")
    st.write(bug["description"])

    with st.form("bug_update_form"):
        new_status = st.selectbox("Status", BUG_STATUSES, index=BUG_STATUSES.index(bug["status"]), key="bug_new_status")
        new_sev = st.selectbox("Severity", SEVERITIES, index=SEVERITIES.index(bug["severity"]), key="bug_new_sev")
        assignee = st.text_input("Assignee", bug.get("assignee") or "", key="bug_assignee")
        notes = st.text_area("Resolution Notes", bug.get("resolution_notes") or "", key="bug_notes")
        if st.form_submit_button("Save changes"):
            update_bug(
                bug["bug_id"],
                status=new_status,
                severity=new_sev,
                assignee=assignee,
                resolution_notes=notes,
            )
            st.success("Updated.")
            st.rerun()
