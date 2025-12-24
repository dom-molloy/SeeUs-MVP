import re

def _extract_numbers(text):
    return [float(x) for x in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)", text or "")]

def _first_0_10(text):
    for n in _extract_numbers(text):
        if 0 <= n <= 10:
            return float(n)
    return None

def _text_similarity(a, b):
    a_tokens = set(re.findall(r"[a-zA-Z']{3,}", (a or "").lower()))
    b_tokens = set(re.findall(r"[a-zA-Z']{3,}", (b or "").lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)

def overall_score(scores):
    vals = [v[0] for v in scores.values() if v[0] > 0]
    return sum(vals) / len(vals) if vals else 0.0

def score_duo(a, b):
    # MVP heuristic: combine numeric closeness gap + token overlap for a few key items
    out = {}

    # Values alignment (rough)
    out["values"] = (4.0 + 6.0*_text_similarity(a.get("values_hierarchy",""), b.get("values_hierarchy","")), 0.5, "Token overlap (MVP).")

    # Cost tolerance (rough—alignment is less important than awareness; still use similarity)
    out["cost"] = (4.0 + 6.0*_text_similarity(a.get("cost_tolerance",""), b.get("cost_tolerance","")), 0.4, "Token overlap (MVP).")

    # Repair capacity (rough)
    out["conflict"] = (4.0 + 6.0*_text_similarity(a.get("repair_capacity",""), b.get("repair_capacity","")), 0.4, "Token overlap (MVP).")

    # Power / decisions
    out["power"] = (4.0 + 6.0*_text_similarity(a.get("power_decisions",""), b.get("power_decisions","")), 0.4, "Token overlap (MVP).")

    # Stress behavior
    out["stress"] = (4.0 + 6.0*_text_similarity(a.get("stress_behavior",""), b.get("stress_behavior","")), 0.4, "Token overlap (MVP).")

    # Attachment numeric gap
    ca = _first_0_10(a.get("closeness_numeric",""))
    cb = _first_0_10(b.get("closeness_numeric",""))
    if ca is not None and cb is not None:
        d = abs(ca - cb)
        out["attachment"] = (9.0 if d<=1 else (7.5 if d<=3 else 6.0), 0.7, f"Closeness distance ~{d:g}.")
    else:
        out["attachment"] = (0.0, 0.2, "Missing numeric closeness.")

    # Agency (not compatibility—risk indicator). Still return as dimension.
    out["agency"] = (4.0 + 6.0*_text_similarity(a.get("agency_choice",""), b.get("agency_choice","")), 0.3, "Token overlap (MVP).")

    return out

def score_solo(a):
    out = {}
    # Provide completeness-based scores so solo report still works.
    for key, dim in [
        ("values_hierarchy","values"),
        ("cost_tolerance","cost"),
        ("repair_capacity","conflict"),
        ("emotional_labor","load"),
        ("closeness_numeric","attachment"),
        ("power_decisions","power"),
        ("stress_behavior","stress"),
        ("pattern_role","pattern"),
        ("future_self","future"),
        ("agency_choice","agency"),
    ]:
        out[dim] = (7.0 if a.get(key) else 0.0, 0.5, "Based on presence of an answer (MVP).")

    # bump if numeric anchor exists
    cn = _first_0_10(a.get("closeness_numeric",""))
    if cn is not None:
        out["attachment"] = (8.0, 0.7, f"Detected closeness ~{cn:g}/10.")
    return out
