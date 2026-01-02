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
from datetime import datetime
from urllib.parse import urlencode

import streamlit as st

from seeus_mvp.question_store import load_question_bank

from seeus_mvp.db import (
    save_report, get_latest_report,
    init_db, upsert_user, create_relationship, list_relationships, get_relationship,
    create_session, get_open_session, end_session, save_response,
    get_answers_for_session, get_last_answers, get_answer_history,
    create_invite, get_invite, mark_invite_used,
    archive_relationship, restore_relationship,
)

# ✅ package-safe import so Streamlit Cloud doesn't load a different bugs.py
from seeus_mvp.bugs import (
    init_bugs_table,
    create_bug, list_bugs, get_bug, update_bug,
    BUG_STATUSES, SEVERITIES, bug_metrics
)

from seeus_mvp.scoring import score_solo, score_duo, overall_score
from seeus_mvp.llm_scoring import score_duo_llm, overall_from_llm
from seeus_mvp.reporting import DIMENSION_ORDER, DIMENSION_LABELS, build_headlines
from seeus_mvp.deep_research import run_deep_research
from seeus_mvp.research_packet import build_key_quotes, detect_contradictions, compute_deltas_over_time
from seeus_mvp.render_brief import render_brief
from seeus_mvp.pdf_export import brief_to_pdf_bytes
from seeus_mvp.growth_ui import render_growth_dashboard


# -------------------- CONFIG --------------------
st.set_page_config(page_title="SeeUs MVP", layout="centered")

# ✅ Avoid blocking/hanging on reruns + surface init errors instead of “loading forever”
@st.cache_resource
def _bootstrap():
    init_db()
    init_bugs_table()
    return True

try:
    _bootstrap()
except Exception as e:
    st.error("Startup failed during initialization.")
    st.exception(e)
    st.stop()

BASE_APP_URL = (os.getenv("BASE_APP_URL") or "").strip() or "https://seeus-mvp-nfbw9pe3pclpgw4kchx9gh.streamlit.app"
DEFAULT_QUESTIONS_URL = "https://raw.githubusercontent.com/dom-molloy/SeeUs-Question-Bank/main/questions_bank.json"


def _get_setting(key: str, default: str = "") -> str:
    # st.secrets throws if no secrets file exists locally
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


def render_change_tracking(rid, QUESTIONS):
    st.subheader("Change tracking (last 3 answers per question)")
    respondent = st.selectbox("Respondent", ["A", "B", "solo"], index=0, key="ct_resp")
    qid = st.selectbox("Question", [q["id"] for q in QUESTIONS], key="ct_qid")
    hist = get_answer_history(rid, respondent, qid, limit=3) or []
    if not hist:
        st.info("No history yet for that question.")
        return
    for i, row in enumerate(hist):
        st.markdown(f"**#{i+1} • {row['created_at']}**")
        st.write(row["answer_text"] or "(blank)")
        st.divider()


def _extract_first_0_10(text):
    import re
    nums = [float(x) for x in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)", text or "")]
    for n in nums:
        if 0 <= n <= 10:
            return n
    return None


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


def _is_archived_row(r) -> bool:
    try:
        return int(r["is_archived"] or 0) == 1
    except Exception:
        return False


# -------------------- INVITE LOCKING --------------------
token = _get_query_param("t")
invite = get_invite(token) if token else None
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


# -------------------- SIDEBAR --------------------
with st.sidebar:
    st.header("SeeUs")
    page = st.radio(
        "Go to",
        ["Assess", "Report", "Growth", "Bug Tracker", "Help"],
        index=0,
        key="page_nav",
    )

    show_archived = st.toggle("Show archived relationships", value=False, key="show_archived")

    st.divider()
    st.subheader("Profile")
    user_id = st.text_input("Your ID", value=st.session_state.get("user_id", "pete"), key="user_id_in")
    display_name = st.text_input("Display name", value=st.session_state.get("display_name", "Pete"), key="display_in")
    if st.button("Save profile", key="save_profile_btn"):
        st.session_state["user_id"] = user_id.strip()
        st.session_state["display_name"] = display_name.strip()
        upsert_user(st.session_state["user_id"], st.session_state["display_name"])
        st.success("Saved.")


# -------------------- HEADER --------------------
st.title("SeeUs — Relationship Mirror")
st.caption("**_Created by Dom Molloy and Feliza Irvin_**")

# -------------------- ROUTING: Bug Tracker / Help --------------------
if page == "Bug Tracker":
    who = st.session_state.get("display_name") or st.session_state.get("user_id") or "unknown"
    render_bug_tracker(who)
    st.stop()

if page == "Help":
    st.header("Help")
    st.markdown(
        """
**Quick start**
1) Set profile in the sidebar → Save  
2) Create or select a relationship  
3) Go to Assess → Start new session → answer questions

**Duo mode**
- Person A creates relationship
- Generate invite link for B (or A)
- Partner opens link → relationship is locked + respondent is locked
- Reports compare A vs B once both complete primary questions
        """
    )
    st.stop()


# -------------------- RELATIONSHIP SELECTION --------------------
include_archived = bool(st.session_state.get("show_archived", False))
rels = list_relationships(include_archived=include_archived) or []
rel_labels = [
    f'{r["label"]}  •  {r["relationship_id"][:8]}' + ("  (archived)" if _is_archived_row(r) else "")
    for r in rels
]

if forced_rid:
    rid = forced_rid
    st.info("Invite link detected — relationship is locked for this session.")
else:
    selected = st.selectbox("Relationship", ["(new)"] + rel_labels, key="rel_select")
    if selected == "(new)":
        st.subheader("Create a relationship")
        label = st.text_input("Label (e.g., 'Me + Bee')", key="new_rel_label")
        other_id = st.text_input("Other person ID (optional)", key="new_rel_other")
        if st.button("Create", key="create_rel_btn"):
            if not st.session_state.get("user_id"):
                st.error("Set your profile in the sidebar first.")
                st.stop()
            new_rid = str(uuid.uuid4())
            create_relationship(
                new_rid,
                st.session_state["user_id"],
                other_id.strip() or None,
                label.strip() or "Untitled",
            )
            st.success(f"Created: {new_rid[:8]}")
            st.rerun()
        st.stop()

    rid = rels[rel_labels.index(selected)]["relationship_id"]

st.session_state["relationship_id"] = rid
relationship = get_relationship(rid)
st.caption(f"Relationship ID: {rid[:8]}  •  Stored in seeus.db")


# -------------------- RELATIONSHIP SETTINGS --------------------
if not forced_rid:
    archived_selected = _is_archived_row(relationship) if relationship else False
    if archived_selected:
        st.warning("This relationship is archived.")
        if st.button("Restore relationship", key="restore_rel_btn"):
            restore_relationship(rid)
            st.success("Restored.")
            st.rerun()

    with st.expander("Relationship settings"):
        st.caption("Archiving hides this relationship from the list (unless 'Show archived' is on). Data is preserved.")
        confirm_archive = st.checkbox("I understand this will archive the relationship.", key="confirm_archive")
        if st.button("Archive relationship", disabled=not confirm_archive, key="archive_rel_btn"):
            archive_relationship(rid)
            st.success("Archived.")
            st.rerun()


# -------------------- INVITE LINK GENERATOR --------------------
def _clipboard_button(label: str, text: str, key: str):
    # Works across Streamlit versions; uses JS clipboard API.
    import streamlit.components.v1 as components
    html = f"""
    <button style="padding:0.4rem 0.7rem;border-radius:8px;border:1px solid #ddd;cursor:pointer;"
      onclick="navigator.clipboard.writeText({json.dumps(text)});">
      {label}
    </button>
    """
    components.html(html, height=45)


if not forced_rid:
    with st.expander("Invite link (Duo mode)"):
        st.write("Generate a tokenized link for Person B (or A).")
        which = st.selectbox("Invite respondent", ["B", "A"], index=0, key="invite_respondent")
        if st.button("Create invite link", key="create_invite_btn"):
            t = str(uuid.uuid4()).replace("-", "")
            create_invite(t, rid, which)
            link = f"{BASE_APP_URL}/?{urlencode({'t': t})}"
            st.session_state["latest_invite_link"] = link

        link = st.session_state.get("latest_invite_link", "")
        if link:
            st.text_input("Invite link", value=link, disabled=True, key="invite_link_box")
            _clipboard_button("Copy invite link", link, key="copy_invite_link")
            st.caption("Copy and send the full link to the other person.")


# -------------------- PAGE ROUTING --------------------
if page == "Growth":
    st.header("Growth")
    open_sess = get_open_session(rid)
    sess_mode = open_sess["mode"] if open_sess else st.session_state.get("mode", "solo")
    if sess_mode == "duo":
        resp = st.selectbox("View as", ["A", "B"], index=0, key="growth_view_as")
    else:
        resp = "solo"
    render_growth_dashboard(rid, mode=sess_mode, respondent=resp)
    st.stop()

if page == "Report":
    st.header("Report (MVP)")

    rows_a = get_last_answers(rid, respondent="A", limit=500) or []
    rows_b = get_last_answers(rid, respondent="B", limit=500) or []
    rows_s = get_last_answers(rid, respondent="solo", limit=500) or []

    # SOLO
    if rows_s and not rows_a and not rows_b:
        amap = latest_map(rows_s)
        scores = score_solo(amap)
        st.metric("Overall (0–10)", f"{overall_score(scores):.1f}")

        st.subheader("Dimension scores")
        for dim in DIMENSION_ORDER:
            if dim in scores:
                s, conf, notes = scores[dim]
                st.write(f"**{DIMENSION_LABELS.get(dim, dim)}:** {s:.1f}  (conf {conf:.2f})")
                st.caption(notes)

        st.subheader("Deep Research Mode")
        st.caption("Generates a Relational Dynamics Brief grounded in your answers. Requires OPENAI_API_KEY.")
        dr_model = st.text_input("Deep Research model", value="gpt-4o-mini", key="dr_model_solo")

        if st.button("Generate Deep Research Brief", key="dr_btn_solo"):
            try:
                bmap = {}
                key_quotes = build_key_quotes(amap, bmap, mode="solo")
                contradictions = detect_contradictions(amap, bmap, mode="solo")

                qids = [q["id"] for q in QUESTIONS]
                deltas = compute_deltas_over_time(get_answer_history, rid, "solo", qids, limit=3)

                # ✅ FIX: avoid fragile long-line list literals that can get mangled
                dimension_scores = []
                for dim_key, tup in scores.items():
                    dimension_scores.append({
                        "dimension": dim_key,
                        "score": float(tup[0]),
                        "confidence": "Medium",
                        "rationale": str(tup[2] or ""),
                    })

                brief = run_deep_research(
                    mode="solo",
                    dimension_scores=dimension_scores,
                    key_quotes=key_quotes,
                    contradictions=contradictions,
                    deltas_over_time=deltas,
                    model=dr_model.strip() or "gpt-4o-mini",
                )
                save_report(str(uuid.uuid4()), rid, "deep", json.dumps(brief, ensure_ascii=False))
                st.success("Deep Research Brief saved.")
                render_brief(brief)

                pdf_bytes = brief_to_pdf_bytes(
                    brief,
                    header={
                        "relationship_label": relationship["label"] if relationship else rid[:8],
                        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
                        "model": dr_model.strip() or "gpt-4o-mini",
                    },
                )
                st.download_button(
                    "Download PDF",
                    data=pdf_bytes,
                    file_name="seeus_relational_dynamics_brief.pdf",
                    mime="application/pdf",
                )
            except Exception as e:
                st.error(f"Deep Research failed: {e}")
                st.info("Tip: set OPENAI_API_KEY in your environment and restart Streamlit.")

        st.divider()
        render_change_tracking(rid, QUESTIONS)
        st.divider()
        render_memory(rid)
        st.stop()

    # DUO
    if rows_a and rows_b:
        amap = latest_map(rows_a)
        bmap = latest_map(rows_b)

        use_llm = st.toggle("Use LLM scoring (OpenAI)", value=False, help="Requires OPENAI_API_KEY.", key="use_llm_duo")
        model = st.text_input("Model", value="gpt-4o-mini", key="llm_model_duo")

        if use_llm:
            try:
                dim_scores = score_duo_llm(amap, bmap, model=model.strip())
                overall_llm = overall_from_llm(dim_scores)
                st.metric("Overall compatibility (LLM, 0–10)", f"{overall_llm:.1f}")

                st.subheader("Dimension scores (LLM)")
                for d in dim_scores:
                    st.write(
                        f"**{DIMENSION_LABELS.get(d['dimension'], d['dimension'])}:** "
                        f"{float(d.get('score', 0)):.1f}  •  {d.get('confidence', '')}"
                    )
                    st.caption(d.get("rationale", ""))

                st.divider()
                render_change_tracking(rid, QUESTIONS)
                st.divider()
                render_memory(rid)
                st.stop()
            except Exception as e:
                st.error(f"LLM scoring failed: {e}")
                st.info("Tip: set OPENAI_API_KEY in your environment then restart Streamlit.")

        scores = score_duo(amap, bmap)
        st.metric("Overall compatibility (0–10)", f"{overall_score(scores):.1f}")

        heads = build_headlines(scores)
        st.subheader("Headlines")
        st.write("**Top strengths**")
        for dim, s in heads["top"]:
            st.write(f"- {DIMENSION_LABELS.get(dim, dim)}: {s:.1f}")
        st.write("**Biggest frictions**")
        for dim, s in heads["bottom"]:
            st.write(f"- {DIMENSION_LABELS.get(dim, dim)}: {s:.1f}")

        st.divider()
        render_change_tracking(rid, QUESTIONS)
        st.divider()
        render_memory(rid)
        st.stop()

    st.info("Not enough data yet for a report. Complete Solo or both A and B.")
    render_change_tracking(rid, QUESTIONS)
    render_memory(rid)
    st.stop()


# -------------------- ASSESS --------------------
st.header("Assess")

st.subheader("Truth temperature")
tone_profile = st.selectbox(
    "How direct do you want this to be?",
    ["Gentle & supportive", "Clear & direct", "No sugarcoating"],
    index=0,
    key="tone_profile",
)
# ✅ DO NOT set st.session_state["tone_profile"] here; Streamlit owns widget state.

# If invite link, force duo
if forced_rid:
    mode = "duo"
else:
    mode = st.selectbox("Assessment mode", ["solo", "duo"], index=0, key="mode_select")

open_sess = get_open_session(rid)
colA, colB = st.columns(2)

with colA:
    if open_sess is None:
        if st.button("Start new session", key="start_session"):
            sid = str(uuid.uuid4())
            create_session(sid, rid, mode, tone_profile=st.session_state.get("tone_profile"))
            st.session_state["session_id"] = sid
            st.session_state["mode"] = mode
            st.success("Session started.")
            st.rerun()
    else:
        st.info(f"Open session: {open_sess['session_id'][:8]} (mode={open_sess['mode']})")
        if st.button("Resume open session", key="resume_session"):
            st.session_state["session_id"] = open_sess["session_id"]
            st.session_state["mode"] = open_sess["mode"]
            st.rerun()

with colB:
    if open_sess is not None and not forced_rid:
        if st.button("End open session", key="end_session"):
            end_session(open_sess["session_id"])
            if st.session_state.get("session_id") == open_sess["session_id"]:
                st.session_state.pop("session_id", None)
            st.success("Ended.")
            st.rerun()

sid = st.session_state.get("session_id")
if not sid:
    render_memory(rid)
    st.stop()

sess_mode = st.session_state.get("mode", mode)
rows_all = get_answers_for_session(sid) or []

# Respondent selection
if sess_mode == "solo":
    respondent = "solo"
else:
    if forced_respondent:
        respondent = forced_respondent
        st.info(f"Invite respondent locked: {respondent}")
        used_key = f"invite_used_{token}"
        if token and not st.session_state.get(used_key, False):
            mark_invite_used(token)
            st.session_state[used_key] = True
    else:
        respondent = st.radio("Who’s answering right now?", ["A", "B"], horizontal=True, key="who_answering")

rows_me = [r for r in rows_all if r["respondent"] == respondent]
answered = set([r["question_id"] for r in rows_me])

# Branch queue (per respondent)
bq_key = f"branch_queue_{sid}_{respondent}"
used_dim_key = f"branch_used_dims_{sid}_{respondent}"
if bq_key not in st.session_state:
    st.session_state[bq_key] = []
if used_dim_key not in st.session_state:
    st.session_state[used_dim_key] = set()


def _queue_branch(question_id: str):
    q0 = QUESTION_BY_ID.get(question_id)
    if not q0:
        return
    dim = q0.get("dimension")
    if dim in st.session_state[used_dim_key]:
        return
    if question_id not in st.session_state[bq_key] and question_id not in answered:
        st.session_state[bq_key].append(question_id)
        st.session_state[used_dim_key].add(dim)


def _maybe_queue_branches(latest_answer_text: str, q_obj: dict):
    branch_id = q_obj.get("branch")
    if not branch_id:
        return
    txt = (latest_answer_text or "").strip()
    if len(txt) < 30:
        _queue_branch(branch_id)


def _next_question_id():
    if st.session_state[bq_key]:
        return st.session_state[bq_key][0]
    for qid in PRIMARY_IDS:
        if qid not in answered:
            return qid
    return None


primary_done = sum([1 for qid in PRIMARY_IDS if qid in answered])
st.divider()
st.progress(min(1.0, primary_done / max(1, len(PRIMARY_IDS))))

mm_key = f"mirror_done_{sid}_{respondent}"
if mm_key not in st.session_state:
    st.session_state[mm_key] = False

if (not st.session_state[mm_key]) and primary_done >= 5:
    st.subheader("Mirror moment")
    vals = next((r["answer_text"] for r in rows_me if r["question_id"] == "values_hierarchy"), "")
    cost = next((r["answer_text"] for r in rows_me if r["question_id"] == "cost_tolerance"), "")
    close = next((r["answer_text"] for r in rows_me if r["question_id"] == "closeness_numeric"), "")
    cn = _extract_first_0_10(close)

    strength = "You’re naming what matters to you with some clarity." if len((vals or "").strip()) >= 40 else "You’re starting to identify what matters most."
    tension = f"Your closeness number is around {cn:g}/10, which can create negotiation around space and contact." if cn is not None else "Closeness/space needs may become a negotiation point."
    cost_line = "You’ve historically carried some discomfort to stay connected." if len((cost or "").strip()) >= 20 else "There may be an unspoken cost you’re willing to pay for connection."

    st.markdown(f"**Strength:** {strength}")
    st.markdown(f"**Tension:** {tension}")
    st.markdown(f"**Cost:** {cost_line}")

    ok = st.radio("Does this feel accurate enough to continue?", ["Yes", "Not quite"], horizontal=True, key="mm_ok")
    if ok == "Not quite":
        correction = st.text_area("What should I understand differently? (Optional)", height=120, key="mm_corr")
        if st.button("Save correction and continue", key="mm_save_corr"):
            save_response(
                response_id=str(uuid.uuid4()),
                session_id=sid,
                relationship_id=rid,
                respondent=respondent,
                question_id="mirror_correction",
                answer_text=correction.strip(),
                answer_json=json.dumps({"dimension": "meta"}),
            )
            st.session_state[mm_key] = True
            st.rerun()
    else:
        if st.button("Continue", key="mm_continue"):
            st.session_state[mm_key] = True
            st.rerun()
    st.stop()

next_qid = _next_question_id()
if next_qid is None:
    st.success(f"{respondent} is done for this session.")
    if sess_mode == "duo":
        done_a = all([qid in set([r["question_id"] for r in rows_all if r["respondent"] == "A"]) for qid in PRIMARY_IDS])
        done_b = all([qid in set([r["question_id"] for r in rows_all if r["respondent"] == "B"]) for qid in PRIMARY_IDS])
        if done_a and done_b:
            st.success("Both A and B are done. Go to **Report**.")
        else:
            st.info("Switch respondent to finish the other side.")
    if st.button("End session now", key="end_session_now") and not forced_rid:
        end_session(sid)
        st.session_state.pop("session_id", None)
        st.success("Session ended.")
        st.rerun()
    st.stop()

q = QUESTION_BY_ID[next_qid]
q_idx = next((i for i, qq in enumerate(QUESTIONS) if qq["id"] == next_qid), 0)

st.markdown(f"### Q{q_idx + 1} of {len(QUESTIONS)}")
st.write(_prompt_for(q, st.session_state.get("tone_profile", "Gentle & supportive")))
answer = st.text_area("Answer", height=140, key=f"ans_{sid}_{respondent}_{q['id']}")

c1, c2 = st.columns([1, 1])
with c1:
    if st.button("Save & next", key="save_next"):
        save_response(
            response_id=str(uuid.uuid4()),
            session_id=sid,
            relationship_id=rid,
            respondent=respondent,
            question_id=q["id"],
            answer_text=answer.strip(),
            answer_json=json.dumps({"dimension": q.get("dimension")}),
        )
        _maybe_queue_branches(answer, q)
        if st.session_state[bq_key] and st.session_state[bq_key][0] == q["id"]:
            st.session_state[bq_key].pop(0)
        st.rerun()

with c2:
    if st.button("Skip", key="skip_btn"):
        save_response(
            response_id=str(uuid.uuid4()),
            session_id=sid,
            relationship_id=rid,
            respondent=respondent,
            question_id=q["id"],
            answer_text="",
            answer_json=json.dumps({"skipped": True, "dimension": q.get("dimension")}),
        )
        if st.session_state[bq_key] and st.session_state[bq_key][0] == q["id"]:
            st.session_state[bq_key].pop(0)
        st.rerun()
