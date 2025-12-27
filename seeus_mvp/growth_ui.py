from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import Dict, Any

import streamlit as st

from db import (
    list_growth_checkins, save_growth_checkin, get_latest_growth_checkin,
    list_growth_reflections, save_growth_reflection,
)

# -------------------- Row-safe helpers --------------------
def _rget(row, key: str, default=None):
    """
    Safe getter for both dict and sqlite3.Row.
    sqlite3.Row supports: row["col"] and row.keys()
    """
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, "keys"):  # sqlite3.Row
        try:
            return row[key] if key in row.keys() else default
        except Exception:
            return default
    return default


def _mini_bar(label: str, value_0_5: int, help_text: str = ""):
    value_0_5 = max(0, min(5, int(value_0_5)))
    blocks = "▓" * value_0_5 + "░" * (5 - value_0_5)
    st.markdown(f"**{label}**  {blocks}")
    if help_text:
        st.caption(help_text)


def _parse_metrics(row) -> Dict[str, Any]:
    try:
        return json.loads(_rget(row, "metrics_json", "") or "{}")
    except Exception:
        return {}


def _month_key_now() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _default_prompt_for_month() -> str:
    prompts = [
        "What feels easier to see now than it did a month ago?",
        "What did you stop pretending about this month?",
        "What did you tolerate automatically — and what did you choose intentionally?",
        "Where did you repair quickly — and where did you avoid?",
    ]
    m = int(datetime.utcnow().strftime("%m"))
    return prompts[(m - 1) % len(prompts)]


def _metrics_from_checkin(pattern_text: str, cost_text: str, repair_choice: str, agency_choice: str) -> Dict[str, int]:
    clarity = 2
    if len((pattern_text or "").strip()) >= 60:
        clarity = 4
    elif len((pattern_text or "").strip()) >= 25:
        clarity = 3

    cost = 3
    heavy_tokens = ["heavy", "exhaust", "resent", "tired", "stuck", "pain", "lonely", "anxious", "burden"]
    t = (cost_text or "").lower()
    if any(tok in t for tok in heavy_tokens):
        cost = 4
    if len((cost_text or "").strip()) >= 80:
        cost = min(5, cost + 1)

    agency_map = {
        "Very intentional": 5,
        "Somewhat intentional": 4,
        "Mixed": 3,
        "Mostly inertia": 2,
    }
    agency = agency_map.get(agency_choice or "", 3)

    if repair_choice == "Still unresolved":
        cost = min(5, cost + 1)
        clarity = max(1, clarity - 1)
    if repair_choice == "Repaired quickly":
        cost = max(1, cost - 1)

    return {"clarity": clarity, "cost": cost, "agency": agency}


def render_growth_dashboard(relationship_id: str, mode: str, respondent: str):
    st.header("SeeUs Growth")
    st.caption("Patterns over time, at a glance. Calm visibility — not a scorecard.")

    cols = st.columns([1, 1, 1])
    with cols[0]:
        st.button("Download latest brief", disabled=True)
    with cols[1]:
        st.button("Export timeline as PDF", disabled=True)
    with cols[2]:
        st.button("Pause Growth", disabled=True)

    st.divider()

    st.subheader("Where things stand right now")
    latest = get_latest_growth_checkin(relationship_id, respondent=None if mode == "duo" else respondent)

    if latest:
        m = _parse_metrics(latest)
        _mini_bar("Clarity", m.get("clarity", 3), "How clear your understanding feels")
        _mini_bar("Cost", m.get("cost", 3), "What this relationship is asking of you")
        _mini_bar("Agency", m.get("agency", 3), "How intentional your choice feels")
        st.caption("These are trends, not scores.")
    else:
        st.info("Once you complete a Growth check-in, you’ll see calm trend bars here.")

    st.divider()

    st.subheader("Your timeline")
    rows = list_growth_checkins(relationship_id, respondent=None if mode == "duo" else respondent, limit=50)
    if not rows:
        st.write("No check-ins yet.")
    else:
        for r in rows:
            month_key = _rget(r, "month_key", "") or ""
            created_at = _rget(r, "created_at", "") or ""
            with st.container(border=True):
                st.markdown(
                    f"**{month_key}**  ·  <span style='color:#666'>{created_at}</span>",
                    unsafe_allow_html=True
                )

                bullets = []
                repair_choice = _rget(r, "repair_choice", "")
                if repair_choice:
                    bullets.append(f"Repair: {repair_choice}")

                shift_text = (_rget(r, "shift_text", "") or "").strip()
                if shift_text:
                    bullets.append("Shift: " + shift_text[:120])

                for b in bullets[:3]:
                    st.markdown(f"- {b}")

                quote = (_rget(r, "pattern_text", "") or "").strip()
                if quote:
                    st.markdown(f"> {quote[:200]}")

                m = _parse_metrics(r)
                c1, c2, c3 = st.columns(3)
                with c1:
                    _mini_bar("Clarity", m.get("clarity", 3))
                with c2:
                    _mini_bar("Cost", m.get("cost", 3))
                with c3:
                    _mini_bar("Agency", m.get("agency", 3))

    st.divider()

    st.subheader("Your next check-in")
    st.caption("No prep. No pressure. Just notice.")

    with st.form("growth_checkin"):
        month_key = st.text_input("Month", value=_month_key_now(), help="YYYY-MM (default is current month).")
        pattern_text = st.text_area("Pattern Awareness — Which familiar pattern showed up most clearly this month?", height=120)
        cost_text = st.text_area("Cost Check — What did this relationship ask you to carry more of than you expected?", height=120)
        repair_choice = st.radio(
            "Repair & tension — When tension appeared, how was it handled most often?",
            ["Repaired quickly", "Repaired eventually", "Avoided", "Still unresolved"],
            horizontal=True
        )
        agency_choice = st.radio(
            "Agency pulse — How intentional does your choice to stay feel right now?",
            ["Very intentional", "Somewhat intentional", "Mixed", "Mostly inertia"],
            horizontal=True
        )
        shift_text = st.text_area("One small shift — Is there one change you want to experiment with next month?", height=100)

        if st.form_submit_button("Save check-in"):
            metrics = _metrics_from_checkin(pattern_text, cost_text, repair_choice, agency_choice)
            save_growth_checkin(
                checkin_id=str(uuid.uuid4()),
                relationship_id=relationship_id,
                mode=mode,
                respondent=respondent,
                month_key=(month_key or _month_key_now()).strip(),
                pattern_text=pattern_text.strip(),
                cost_text=cost_text.strip(),
                repair_choice=repair_choice,
                agency_choice=agency_choice,
                shift_text=shift_text.strip(),
                metrics_json=json.dumps(metrics),
            )
            st.success("Saved. Nothing to fix. Nothing to decide — just something you can now see.")
            st.rerun()

    st.divider()

    st.subheader("Reflection prompt")
    prompt = _default_prompt_for_month()
    st.caption(prompt)

    with st.form("growth_reflection"):
        response = st.text_area("Optional response", height=100)
        if st.form_submit_button("Save reflection"):
            if response.strip():
                save_growth_reflection(
                    reflection_id=str(uuid.uuid4()),
                    relationship_id=relationship_id,
                    respondent=respondent,
                    month_key=_month_key_now(),
                    prompt_text=prompt,
                    response_text=response.strip(),
                )
                st.success("Saved.")
                st.rerun()
            else:
                st.info("Nothing to save.")

    refl = list_growth_reflections(relationship_id, respondent=respondent, limit=20)
    if refl:
        with st.expander("Previous reflections"):
            for rr in refl:
                st.markdown(f"**{_rget(rr, 'month_key', '')}** · {_rget(rr, 'created_at', '')}")
                st.caption(_rget(rr, "prompt_text", "") or "")
                st.write(_rget(rr, "response_text", "") or "")
                st.divider()
