# seeus_mvp/app.py

# Optional: load .env locally. Safe on Streamlit Cloud even if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import json
import uuid
from datetime import datetime
from urllib.parse import urlencode

import streamlit as st

# -------------------- PACKAGE-SAFE IMPORTS --------------------
try:
    from seeus_mvp.question_store import load_question_bank
except ModuleNotFoundError:
    from question_store import load_question_bank

try:
    from seeus_mvp.db import (
        save_report,
        get_latest_report,
        init_db,
        upsert_user,
        create_relationship,
        list_relationships,
        get_relationship,
        create_session,
        get_open_session,
        end_session,
        save_response,
        get_answers_for_session,
        get_last_answers,
        get_answer_history,
        create_invite,
        get_invite,
        mark_invite_used,
        archive_relationship,
        restore_relationship,
    )
except ModuleNotFoundError:
    from db import (
        save_report,
        get_latest_report,
        init_db,
        upsert_user,
        create_relationship,
        list_relationships,
        get_relationship,
        create_session,
        get_open_session,
        end_session,
        save_response,
        get_answers_for_session,
        get_last_answers,
        get_answer_history,
        create_invite,
        get_invite,
        mark_invite_used,
        archive_relationship,
        restore_relationship,
    )

# ✅ package-safe import so Streamlit Cloud doesn't load a different bugs.py
try:
    from seeus_mvp.bugs import (
        init_bugs_table,
        create_bug,
        list_bugs,
        get_bug,
        update_bug,
        BUG_STATUSES,
        SEVERITIES,
        bug_metrics,
    )
except ModuleNotFoundError:
    from bugs import (
        init_bugs_table,
        create_bug,
        list_bugs,
        get_bug,
        update_bug,
        BUG_STATUSES,
        SEVERITIES,
        bug_metrics,
    )

try:
    from seeus_mvp.scoring import score_solo, score_duo, overall_score
except ModuleNotFoundError:
    from scoring import score_solo, score_duo, overall_score

# -------------------- CONFIG --------------------
st.set_page_config(page_title="SeeUs MVP", layout="centered")

# Initialize core DB + bugs table (this is the key addition)
init_db()
init_bugs_table()


# -------------------- BUGS ADMIN VIEW --------------------
def render_bugs_admin():
    import pandas as pd

    st.header("🐞 Bugs")

    bugs = list_bugs()  # expected: list[dict]
    if not bugs:
        st.info("No bugs found.")
        return

    df = pd.DataFrame(bugs)

    # Filters
    col1, col2, col3 = st.columns(3)

    status_filter = []
    severity_filter = []

    if "status" in df.columns:
        with col1:
            status_filter = st.multiselect(
                "Status",
                sorted(df["status"].dropna().unique().tolist()),
            )

    if "severity" in df.columns:
        with col2:
            severity_filter = st.multiselect(
                "Severity",
                sorted(df["severity"].dropna().unique().tolist()),
            )

    with col3:
        search = st.text_input("Search", placeholder="title, description, reporter...")

    filtered = df.copy()

    if status_filter and "status" in filtered.columns:
        filtered = filtered[filtered["status"].isin(status_filter)]

    if severity_filter and "severity" in filtered.columns:
        filtered = filtered[filtered["severity"].isin(severity_filter)]

    if search:
        s = search.lower()
        mask = False
        for c in filtered.columns:
            if str(filtered[c].dtype) == "object":
                mask = mask | filtered[c].fillna("").str.lower().str.contains(s)
        filtered = filtered[mask]

    if "created_at" in filtered.columns:
        filtered = filtered.sort_values("created_at", ascending=False)

    st.caption(f"Showing {len(filtered)} of {len(df)} bugs")
    st.dataframe(filtered, use_container_width=True, hide_index=True)

    # Detail + update
    id_col = None
    for candidate in ["id", "bug_id", "uuid"]:
        if candidate in df.columns:
            id_col = candidate
            break

    if not id_col:
        st.warning("No obvious bug id column found (expected 'id' or similar). Showing table only.")
        return

    # Use filtered IDs if possible (prevents selecting hidden rows)
    id_options = filtered[id_col].tolist()
    selected_id = st.selectbox("Open a bug", options=id_options)

    bug = get_bug(selected_id)
    if not bug:
        st.error("Could not load selected bug.")
        return

    st.subheader("Bug details")
    st.json(bug)

    c1, c2 = st.columns(2)

    new_status = None
    new_severity = None

    if "status" in bug:
        with c1:
            current = bug.get("status")
            idx = BUG_STATUSES.index(current) if current in BUG_STATUSES else 0
            new_status = st.selectbox("Update status", BUG_STATUSES, index=idx)

    if "severity" in bug:
        with c2:
            current = bug.get("severity")
            idx = SEVERITIES.index(current) if current in SEVERITIES else 0
            new_severity = st.selectbox("Update severity", SEVERITIES, index=idx)

    if st.button("Save updates", type="primary"):
        updates = {}
        if new_status is not None:
            updates["status"] = new_status
        if new_severity is not None:
            updates["severity"] = new_severity

        if updates:
            update_bug(selected_id, **updates)
            st.success("Updated.")
            st.rerun()
        else:
            st.info("No changes to save.")


# -------------------- MAIN APP (YOUR EXISTING UI) --------------------
def render_seeus_app():
    """
    Paste your existing SeeUs app UI/flow inside this function.

    IMPORTANT:
    - Do NOT remove the init_db() / init_bugs_table() calls above.
    - The Bugs admin view is now accessible via the sidebar Page selector.
    """

    # --- EXISTING APP CONTENT START ---
    st.title("SeeUs MVP")
    st.caption("Your main app flow goes here. Paste your existing app.py body into render_seeus_app().")
    # --- EXISTING APP CONTENT END ---


# -------------------- NAV --------------------
with st.sidebar:
    page = st.radio("Page", ["SeeUs", "Bugs"], index=0)

if page == "Bugs":
    render_bugs_admin()
    st.stop()

# Default
render_seeus_app()
