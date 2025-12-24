from __future__ import annotations
from io import BytesIO
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

def _safe(s: Any) -> str:
    if s is None:
        return ""
    return str(s)

def brief_to_pdf_bytes(brief: Dict[str, Any], header: Dict[str, str] | None = None) -> bytes:
    """Create a polished PDF from a Deep Research brief JSON."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.8*inch,
        rightMargin=0.8*inch,
        topMargin=0.8*inch,
        bottomMargin=0.8*inch,
        title=_safe(brief.get("title", "Relational Dynamics Brief"))
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SeeUsTitle",
        parent=styles["Title"],
        textColor=colors.HexColor("#111111"),
        spaceAfter=12,
    )
    h_style = ParagraphStyle(
        "SeeUsH2",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#111111"),
        spaceBefore=10,
        spaceAfter=6,
    )
    b_style = ParagraphStyle(
        "SeeUsBody",
        parent=styles["BodyText"],
        leading=14,
        spaceAfter=6,
    )
    small_style = ParagraphStyle(
        "SeeUsSmall",
        parent=styles["BodyText"],
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#444444"),
        spaceAfter=6,
    )

    flow = []
    flow.append(Paragraph(_safe(brief.get("title", "Relational Dynamics Brief")), title_style))

    if header:
        meta_lines = []
        for k in ["relationship_label", "generated_at", "model"]:
            v = header.get(k)
            if v:
                meta_lines.append(f"<b>{k.replace('_',' ').title()}:</b> {_safe(v)}")
        if meta_lines:
            flow.append(Paragraph("<br/>".join(meta_lines), small_style))
            flow.append(Spacer(1, 6))

    def add_list(items: List[str]):
        lf = ListFlowable(
            [ListItem(Paragraph(_safe(x), b_style), leftIndent=14) for x in items],
            bulletType="bullet",
            leftIndent=14,
        )
        flow.append(lf)

    # Observed patterns
    flow.append(Paragraph("Observed patterns", h_style))
    patterns = brief.get("observed_patterns") or []
    if not patterns:
        flow.append(Paragraph("No patterns available.", b_style))
    else:
        for p in patterns:
            flow.append(Paragraph(f"<b>{_safe(p.get('headline'))}</b>", b_style))
            evidence = p.get("evidence") or []
            if evidence:
                add_list(evidence[:6])
            why = _safe(p.get("why_it_matters"))
            if why:
                flow.append(Paragraph(f"<i>Why it matters:</i> {why}", b_style))
            flow.append(Spacer(1, 6))

    # What tends to happen
    flow.append(Paragraph("What tends to happen", h_style))
    wth = brief.get("what_tends_to_happen") or []
    if wth:
        for item in wth[:6]:
            flow.append(Paragraph(f"<b>{_safe(item.get('headline'))}</b>", b_style))
            mech = _safe(item.get("mechanism"))
            cond = _safe(item.get("conditions"))
            if mech:
                flow.append(Paragraph(f"<i>Mechanism:</i> {mech}", b_style))
            if cond:
                flow.append(Paragraph(f"<i>Conditions:</i> {cond}", b_style))
            flow.append(Spacer(1, 6))
    else:
        flow.append(Paragraph("No items available.", b_style))

    # Early wins
    flow.append(Paragraph("Early wins", h_style))
    early = brief.get("early_wins") or []
    if early:
        add_list(early[:10])
    else:
        flow.append(Paragraph("None listed.", b_style))

    # Failure modes
    flow.append(Paragraph("Likely failure modes", h_style))
    fms = brief.get("likely_failure_modes") or []
    if fms:
        for fm in fms[:8]:
            name = _safe(fm.get("name"))
            risk = _safe(fm.get("risk_level"))
            flow.append(Paragraph(f"<b>{name}</b> <font color='#666666'>(risk: {risk})</font>", b_style))
            hs = _safe(fm.get("how_it_starts"))
            he = _safe(fm.get("how_it_ends"))
            if hs:
                flow.append(Paragraph(f"<i>How it starts:</i> {hs}", b_style))
            if he:
                flow.append(Paragraph(f"<i>How it ends:</i> {he}", b_style))
            flow.append(Spacer(1, 6))
    else:
        flow.append(Paragraph("None listed.", b_style))

    # Leverage points
    flow.append(Paragraph("Leverage points", h_style))
    lps = brief.get("leverage_points") or []
    if lps:
        for lp in lps[:8]:
            action = _safe(lp.get("action"))
            why = _safe(lp.get("why"))
            how = _safe(lp.get("how_to_try"))
            flow.append(Paragraph(f"<b>{action}</b>", b_style))
            if why:
                flow.append(Paragraph(f"<i>Why:</i> {why}", b_style))
            if how:
                flow.append(Paragraph(f"<i>How to try:</i> {how}", b_style))
            flow.append(Spacer(1, 6))
    else:
        flow.append(Paragraph("None listed.", b_style))

    # Stay/Change/Leave lens
    scl = brief.get("stay_change_leave_lens") or {}
    flow.append(Paragraph("Stay / Change / Leave lens", h_style))
    flow.append(Paragraph(f"<b>Stay as-is:</b> {_safe(scl.get('stay_as_is'))}", b_style))
    flow.append(Paragraph(f"<b>Change one thing:</b> {_safe(scl.get('change_one_thing'))}", b_style))
    flow.append(Paragraph(f"<b>If nothing changes:</b> {_safe(scl.get('if_nothing_changes'))}", b_style))

    # Follow-ups + limits
    flow.append(Paragraph("Follow-up questions", h_style))
    fu = brief.get("follow_up_questions") or []
    if fu:
        add_list(fu[:10])
    else:
        flow.append(Paragraph("None.", b_style))

    flow.append(Paragraph("Limits", h_style))
    lim = brief.get("limits") or []
    if lim:
        add_list(lim[:10])
    else:
        flow.append(Paragraph("None.", b_style))

    doc.build(flow)
    return buf.getvalue()
