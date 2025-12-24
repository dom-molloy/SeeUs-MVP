from __future__ import annotations
from typing import Dict, Any, List
import streamlit as st

def render_brief(brief: Dict[str, Any]):
    st.subheader(brief.get("title", "Relational Dynamics Brief"))

    def sec(title: str):
        st.markdown(f"### {title}")

    sec("Observed patterns")
    patterns = brief.get("observed_patterns") or []
    if not patterns:
        st.info("No patterns available.")
    for p in patterns:
        st.markdown(f"**{p.get('headline','')}**")
        evidence = p.get("evidence") or []
        if evidence:
            st.markdown("**Evidence (from your answers):**")
            for e in evidence[:6]:
                st.markdown(f"- {e}")
        w = p.get("why_it_matters")
        if w:
            st.markdown(f"**Why it matters:** {w}")
        st.divider()

    sec("What tends to happen")
    wth = brief.get("what_tends_to_happen") or []
    if not wth:
        st.write("None listed.")
    for item in wth[:6]:
        st.markdown(f"**{item.get('headline','')}**")
        if item.get("mechanism"):
            st.markdown(f"- **Mechanism:** {item.get('mechanism')}")
        if item.get("conditions"):
            st.markdown(f"- **Conditions:** {item.get('conditions')}")

    sec("Early wins")
    ew = brief.get("early_wins") or []
    if ew:
        for x in ew[:10]:
            st.markdown(f"- {x}")
    else:
        st.write("None listed.")

    sec("Likely failure modes")
    fms = brief.get("likely_failure_modes") or []
    if not fms:
        st.write("None listed.")
    for fm in fms[:8]:
        st.markdown(f"**{fm.get('name','')}**  _(risk: {fm.get('risk_level','')})_")
        if fm.get("how_it_starts"):
            st.markdown(f"- **How it starts:** {fm.get('how_it_starts')}")
        if fm.get("how_it_ends"):
            st.markdown(f"- **How it ends:** {fm.get('how_it_ends')}")

    sec("Leverage points")
    lps = brief.get("leverage_points") or []
    if not lps:
        st.write("None listed.")
    for lp in lps[:8]:
        st.markdown(f"**{lp.get('action','')}**")
        if lp.get("why"):
            st.markdown(f"- **Why:** {lp.get('why')}")
        if lp.get("how_to_try"):
            st.markdown(f"- **How to try:** {lp.get('how_to_try')}")

    sec("Stay / Change / Leave lens")
    scl = brief.get("stay_change_leave_lens") or {}
    st.markdown(f"**Stay as-is:** {scl.get('stay_as_is','')}")
    st.markdown(f"**Change one thing:** {scl.get('change_one_thing','')}")
    st.markdown(f"**If nothing changes:** {scl.get('if_nothing_changes','')}")

    sec("Follow-up questions")
    fu = brief.get("follow_up_questions") or []
    if fu:
        for x in fu[:10]:
            st.markdown(f"- {x}")
    else:
        st.write("None.")

    sec("Limits")
    lim = brief.get("limits") or []
    if lim:
        for x in lim[:10]:
            st.markdown(f"- {x}")
    else:
        st.write("None.")
