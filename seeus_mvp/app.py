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
    page = st.radio("Go to", ["Assess", "Report", "Growth", "Help"], index=0, key="page")

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


# -------------------- HELP (reachable anytime) --------------------
if page == "Help":
    st.header("Help & Getting Started")
    st.markdown("""
**What is SeeUs?**  
SeeUs helps individuals and pairs reflect on patterns, alignment, and growth in relationships.

**Quick Start**
1) Set your profile (left sidebar) → **Save profile**  
2) Create/select a relationship  
3) Go to **Assess** and answer questions

**Duo mode**
- Create invite link → send to the other person
- Their link locks the relationship + respondent automatically

**Report**
- Summaries and optional Deep Research (requires OPENAI_API_KEY)

**Growth**
- Monthly check-ins to track trends over time
""")
    st.stop()


# -------------------- RELATIONSHIP SELECT / LOCK --------------------
include_archived = bool(st.session_state.get("show_archived", False))

# If invite link: lock relationship immediately + show it clearly.
if forced_rid:
    rid = forced_rid
    relationship = get_relationship(rid)
    label = (relationship["label"] if relationship else "(unknown relationship)")
    st.info(f"Invite link detected — **locked** to: **{label}**  •  {rid[:8]}")
    st.session_state["relationship_id"] = rid

else:
    rels = list_relationships(include_archived=include_archived) or []
    rel_labels = [
        f'{r["label"]}  •  {r["relationship_id"][:8]}' + ("  (archived)" if _is_archived_row(r) else "")
        for r in rels
    ]

    selected = st.selectbox("Relationship", ["(new)"] + rel_labels, key="rel_select")

    if selected == "(new)":
        st.subheader("Create a relationship")
        label = st.text_input("Label (e.g., 'Me + Tricia')")
        other_id = st.text_input("Other person ID (optional)")

        if st.button("Create"):
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
# Invite link generator (only when not using invite link)
if not forced_rid:
    with st.expander("Invite link (Duo mode)"):
        st.write("Generate a tokenized link for Person B (or A).")
        which = st.selectbox("Invite respondent", ["B", "A"], index=0)

        if st.button("Create invite link"):
            t = str(uuid.uuid4()).replace("-", "")
            create_invite(t, rid, which)

            BASE_APP_URL = "https://seeus-mvp-nfbw9pe3pclpgw4kchx9gh.streamlit.app"
            qs = urlencode({"t": t})
            invite_url = f"{BASE_APP_URL}/?{qs}"

            # ✅ Copyable code block (adds a copy button automatically)
            st.code(invite_url)
            st.caption("⬆ Hover and click the copy icon to copy the invite link.")
            # Optional visual affordance
            st.caption("Click the copy icon to copy the invite link and send it to the other person.")

# -------------------- RELATIONSHIP SETTINGS --------------------
# Disable archive/restore controls when using invite link (prevents partner from hiding it)
if not forced_rid:
    archived_selected = _is_archived_row(relationship) if relationship else False
    if archived_selected:
        st.warning("This relationship is archived.")
        if st.button("Restore relationship"):
            restore_relationship(rid)
            st.success("Restored.")
            st.rerun()

    with st.expander("Relationship settings"):
        st.caption("Archiving hides this relationship from the list. Data is preserved.")
        confirm_archive = st.checkbox("I understand this will archive the relationship.", key="confirm_archive")
        if st.button("Archive relationship", disabled=not confirm_archive):
            archive_relationship(rid)
            st.success("Archived.")
            st.rerun()


# -------------------- INVITE LINK GENERATOR --------------------
if not forced_rid:
    with st.expander("Invite link (Duo mode)"):
        st.write("Generate a tokenized link for Person B (or A).")
        which = st.selectbox(
    "Invite respondent",
    ["B", "A"],
    index=0,
    key="invite_respondent_select"
)
        if st.button("Create invite link", key="create_invite_button"):
            t = str(uuid.uuid4()).replace("-", "")
            create_invite(t, rid, which)
            qs = urlencode({"t": t})
            st.code(f"{BASE_APP_URL}/?{qs}")
            st.caption("Copy the full link and send it to the other person.")


# -------------------- PAGE ROUTING --------------------
if page == "Report":
    st.header("Report (MVP)")

    rows_a = get_last_answers(rid, respondent="A", limit=500) or []
    rows_b = get_last_answers(rid, respondent="B", limit=500) or []
    rows_s = get_last_answers(rid, respondent="solo", limit=500) or []

    # ---------- SOLO REPORT ----------
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
        dr_model = st.text_input("Deep Research model", value="gpt-4o-mini")

        if st.button("Generate Deep Research Brief"):
            try:
                bmap = {}
                key_quotes = build_key_quotes(amap, bmap, mode="solo")
                contradictions = detect_contradictions(amap, bmap, mode="solo")
                qids = [q["id"] for q in QUESTIONS]
                deltas = compute_deltas_over_time(get_answer_history, rid, "solo", qids, limit=3)

                dimension_scores = [
                    {"dimension": dim_key, "score": float(tup[0]), "confidence": "Medium", "rationale": tup[2]}
                    for dim_key, tup in scores.items()
                ]

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
        render_change_tracking(rid)
        st.divider()
        render_memory(rid)
        st.stop()

    # ---------- DUO REPORT ----------
    if rows_a and rows_b:
        amap = latest_map(rows_a)
        bmap = latest_map(rows_b)

        use_llm = st.toggle("Use LLM scoring (OpenAI)", value=False, help="Requires OPENAI_API_KEY in your environment.")
        model = st.text_input("Model", value="gpt-4o-mini")

        if use_llm:
            try:
                dim_scores = score_duo_llm(amap, bmap, model=model.strip())
                overall_llm = overall_from_llm(dim_scores)
                st.metric("Overall compatibility (LLM, 0–10)", f"{overall_llm:.1f}")

                st.subheader("Dimension scores (LLM)")
                for d in dim_scores:
                    st.write(f"**{DIMENSION_LABELS.get(d['dimension'], d['dimension'])}:** {float(d.get('score', 0)):.1f}  •  {d.get('confidence', '')}")
                    st.caption(d.get("rationale", ""))

                st.divider()
                render_change_tracking(rid)
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
        render_change_tracking(rid)
        st.divider()
        render_memory(rid)
        st.stop()

    st.info("Not enough data yet for a report. Complete Solo or both A and B.")
    render_change_tracking(rid)
    render_memory(rid)
    st.stop()


if page == "Growth":
    st.header("Growth")

    open_sess = get_open_session(rid)
    sess_mode = open_sess["mode"] if open_sess else st.session_state.get("mode", "solo")

    if sess_mode == "duo":
        resp = st.selectbox("View as", ["A", "B"], index=0)
    else:
        resp = "solo"

    render_growth_dashboard(rid, mode=sess_mode, respondent=resp)
    st.stop()


# -------------------- ASSESS (default) --------------------
st.header("Assess")

st.subheader("Truth temperature")
tone_profile = st.selectbox(
    "How direct do you want this to be?",
    ["Gentle & supportive", "Clear & direct", "No sugarcoating"],
    index=0,
)
st.session_state["tone_profile"] = tone_profile

# If invite link: force duo
if forced_rid:
    mode = "duo"
else:
    mode = st.selectbox("Assessment mode", ["solo", "duo"], index=0)

open_sess = get_open_session(rid)
colA, colB = st.columns(2)

with colA:
    if open_sess is None:
        if st.button("Start new session"):
            sid = str(uuid.uuid4())
            create_session(sid, rid, mode, tone_profile=st.session_state.get("tone_profile"))
            st.session_state["session_id"] = sid
            st.session_state["mode"] = mode
            st.success("Session started.")
            st.rerun()
    else:
        st.info(f"Open session: {open_sess['session_id'][:8]} (mode={open_sess['mode']})")
        if st.button("Resume open session"):
            st.session_state["session_id"] = open_sess["session_id"]
            st.session_state["mode"] = open_sess["mode"]
            st.rerun()

with colB:
    # Don’t let invite-user end the session from their side
    if open_sess is not None and not forced_rid:
        if st.button("End open session"):
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
        respondent = st.radio("Who’s answering right now?", ["A", "B"], horizontal=True)

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

    ok = st.radio("Does this feel accurate enough to continue?", ["Yes", "Not quite"], horizontal=True)
    if ok == "Not quite":
        correction = st.text_area("What should I understand differently? (Optional)", height=120)
        if st.button("Save correction and continue"):
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
        if st.button("Continue"):
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
    if st.button("End session now") and not forced_rid:
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
    if st.button("Save & next"):
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
    if st.button("Skip"):
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