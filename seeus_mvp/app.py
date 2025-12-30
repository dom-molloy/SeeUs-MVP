# Optional: load .env locally. Safe on Streamlit Cloud even if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import os
import json
import uuid
from datetime import datetime
from urllib.parse import urlencode

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

# ✅ UPDATED: Bug tracker imports (package-safe for Streamlit Cloud)
from seeus_mvp.bugs import (
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

# If you set this on Streamlit Cloud (Secrets) or locally (env), the invite link becomes portable.
BASE_APP_URL = (os.getenv("BASE_APP_URL") or "").strip() or "https://seeus-mvp-nfbw9pe3pclpgw4kchx9gh.streamlit.app"

# Optional: provide a default questions URL so local dev works even without secrets.toml/env.
DEFAULT_QUESTIONS_URL = "https://raw.githubusercontent.com/dom-molloy/SeeUs-Question-Bank/main/questions_bank.json"


# -------------------- HELPERS --------------------
def _get_setting(key: str, default: str = "") -> str:
    # st.secrets throws if no secrets.toml exists; guard hard.
    try:
        return str(st.secrets[key])
    except Exception:
        return str(os.getenv(key, default) or default)

def _get_query_param(name: str):
    # New Streamlit API
    try:
        v = st.query_params.get(name)
        if isinstance(v, (list, tuple)):
            return v[0] if v else None
        return v
    except Exception:
        pass

    # Old Streamlit API fallback
    try:
        qp = st.experimental_get_query_params()
        v = qp.get(name, [None])
        return v[0] if isinstance(v, list) else v
    except Exception:
        return None

def answered_ids(rows):
    return set([r["question_id"] for r in rows])

def latest_map(rows_desc):
    m = {}
    for r in reversed(rows_desc):  # newest overwrites
        m[r["question_id"]] = r["answer_text"]
    return m

def render_memory(rid):
    st.subheader("What I remember (latest answers)")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Latest (A / solo)**")
        for r in get_last_answers(rid, respondent="A", limit=6) or []:
            st.write(f"- {r['question_id']}: {str(r['answer_text'] or '')[:90]}")
        for r in get_last_answers(rid, respondent="solo", limit=6) or []:
            st.write(f"- {r['question_id']}: {str(r['answer_text'] or '')[:90]}")
    with c2:
        st.markdown("**Latest (B)**")
        for r in get_last_answers(rid, respondent="B", limit=6) or []:
            st.write(f"- {r['question_id']}: {str(r['answer_text'] or '')[:90]}")

def render_change_tracking(rid):
    st.subheader("Change tracking (last 3 answers per question)")
    respondent = st.selectbox("Respondent", ["A", "B", "solo"], index=0)
    qid = st.selectbox("Question", [q["id"] for q in QUESTIONS])
    hist = get_answer_history(rid, respondent, qid, limit=3) or []
    if not hist:
        st.info("No history yet for that question.")
        return
    for i, row in enumerate(hist):
        st.markdown(f"**#{i+1} • {row['created_at']}**")
        st.write(row["answer_text"] or "(blank)")
        st.divider()

def _tone_key(tone: str) -> str:
    t = (tone or "Gentle").lower()
    if "sugar" in t or "sharp" in t:
        return "sharp"
    if "clear" in t or "direct" in t:
        return "clear"
    if "gentle" in t:
        return "gentle"
    return "default"

def _prompt_for(q, tone: str) -> str:
    key = _tone_key(tone)
    pr = q.get("prompt") or {}
    return pr.get(key) or pr.get("default") or q.get("text") or ""

def _extract_first_0_10(text):
    import re
    nums = [float(x) for x in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)", text or "")]
    for n in nums:
        if 0 <= n <= 10:
            return n
    return None

def _is_archived_row(r) -> bool:
    try:
        return int(r["is_archived"] or 0) == 1
    except Exception:
        return False


# ✅ NEW: Bug Tracker UI
def render_bug_tracker(current_user: str):
    st.header("🐞 Bug Tracker")

    # Metrics
    m = bug_metrics()
    c1, c2, c3 = st.columns(3)
    c1.metric("Open Critical", m["open_critical"])
    c2.metric("Total Bugs", sum(m["by_status"].values()) if m["by_status"] else 0)
    c3.metric("Closed", m["by_status"].get("Closed", 0))

    st.divider()

    # Create bug
    with st.expander("Report a bug", expanded=False):
        with st.form("bug_create_form"):
            title = st.text_input("Title", placeholder="Short summary")
            desc = st.text_area("Description", placeholder="Steps to reproduce, expected vs actual")
            severity = st.selectbox("Severity", SEVERITIES, index=1)
            submit = st.form_submit_button("Submit")

            if submit:
                if not title.strip() or not desc.strip():
                    st.error("Title and Description are required.")
                else:
                    create_bug(
                        title=title,
                        description=desc,
                        reporter=current_user or "unknown",
                        severity=severity
                    )
                    st.success("Bug submitted.")
                    st.rerun()

    st.divider()

    # Filters
    f1, f2, f3, f4 = st.columns([1, 1, 1, 2])
    status = f1.selectbox("Status", ["All"] + BUG_STATUSES)
    sev = f2.selectbox("Severity", ["All"] + SEVERITIES)
    assignee = f3.text_input("Assignee (exact)", placeholder="leave blank = any")
    search = f4.text_input("Search", placeholder="title/description/reporter/assignee")

    bugs = list_bugs(
        status=status,
        severity=sev,
        assignee=assignee.strip() or None,
        search=search.strip() or None,
        limit=300
    )

    if not bugs:
        st.info("No bugs match your filters.")
        return

    # Select bug
    label_to_id = {
        f"[{b['status']}] ({b['severity']}) {b['title']}": b["id"]
        for b in bugs
    }
    selected_label = st.selectbox("Select a bug", list(label_to_id.keys()))
    bug_id = label_to_id[selected_label]
    bug = get_bug(bug_id)

    if not bug:
        st.error("Bug not found.")
        return

    st.subheader("Details")
    st.write(f"**ID:** `{bug['id']}`")
    st.write(f"**Reporter:** {bug['reporter']}")
    st.write(f"**Assignee:** {bug['assignee'] or '(Unassigned)'}")
    st.write(f"**Created:** {bug['created_at']}")
    st.write(f"**Updated:** {bug['updated_at']}")
    st.write("**Description**")
    st.write(bug["description"])

    st.divider()

    # Update bug
    st.subheader("Update")
    with st.form("bug_update_form"):
        new_status = st.selectbox("Status", BUG_STATUSES, index=BUG_STATUSES.index(bug["status"]))
        new_assignee = st.text_input("Assignee", value=bug["assignee"] or "")
        notes = st.text_area("Resolution notes", value=bug["resolution_notes"] or "")

        save = st.form_submit_button("Save update")
        if save:
            try:
                update_bug(
                    bug_id,
                    status=new_status,
                    assignee=new_assignee,
                    resolution_notes=notes
                )
                st.success("Updated.")
                st.rerun()
            except Exception as e:
                st.error(str(e))


# -------------------- INVITE LOCKING (ONE PLACE ONLY) --------------------
token = _get_query_param("t")
invite = get_invite(token) if token else None

if token and not invite:
    st.error("This invite link is invalid or expired (token not found).")
    st.stop()

forced_rid = invite["relationship_id"] if invite else None
forced_respondent = invite["respondent"] if invite else None


# -------------------- QUESTION BANK --------------------
REMOTE_QUESTIONS_URL = (_get_setting("QUESTIONS_URL", "") or os.getenv("QUESTIONS_URL", "")).strip()
if not REMOTE_QUESTIONS_URL:
    REMOTE_QUESTIONS_URL = DEFAULT_QUESTIONS_URL

QUESTIONS = load_question_bank(REMOTE_QUESTIONS_URL)
QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}
PRIMARY_IDS = [q["id"] for q in QUESTIONS if q.get("is_primary")]


# -------------------- UI: SIDEBAR --------------------
with st.sidebar:
    st.header("SeeUs")
    # ✅ UPDATED: added Bug Tracker
    page = st.radio("Go to", ["Assess", "Report", "Growth", "Bug Tracker", "Help"], index=0, key="page")

    show_archived = st.toggle("Show archived relationships", value=False, key="show_archived")

    st.divider()
    st.subheader("Profile")
    user_id = st.text_input("Your ID", value=st.session_state.get("user_id", "pete"))
    display_name = st.text_input("Display name", value=st.session_state.get("display_name", "Pete"))
    if st.button("Save profile"):
        st.session_state["user_id"] = user_id.strip()
        st.session_state["display_name"] = display_name.strip()
        upsert_user(st.session_state["user_id"], st.session_state["display_name"])
        st.success("Saved.")


# -------------------- HEADER --------------------
st.title("SeeUs — Relationship Mirror")
st.caption("**_Created by Dom Molloy and Feliza Irvin_**")
