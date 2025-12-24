from typing import Dict, List, Any, Tuple
from questions import QUESTIONS

def build_key_quotes(latest_a: Dict[str, str], latest_b: Dict[str, str], mode: str) -> Dict[str, List[str]]:
    # Keep it simple: 1 quote per question, grouped by dimension.
    q_lookup = {q["id"]: q for q in QUESTIONS}
    grouped: Dict[str, List[str]] = {}

    def add(person_label: str, answers: Dict[str, str]):
        for qid, ans in answers.items():
            if ans is None:
                continue
            ans = ans.strip()
            if not ans:
                continue
            dim = q_lookup.get(qid, {}).get("dimension", "other")
            grouped.setdefault(dim, []).append(f"{person_label}: {ans[:280]}")

    if mode == "solo":
        add("Solo", latest_a)
    else:
        add("A", latest_a)
        add("B", latest_b)

    # cap to 2 per dimension for prompt efficiency
    for dim in list(grouped.keys()):
        grouped[dim] = grouped[dim][:2]
    return grouped

def detect_contradictions(latest_a: Dict[str, str], latest_b: Dict[str, str], mode: str) -> List[Dict[str, Any]]:
    # MVP contradiction checks (non-clinical).
    out: List[Dict[str, Any]] = []

    def find_closeness(text: str):
        import re
        nums = [float(x) for x in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)", text or "")]
        for n in nums:
            if 0 <= n <= 10:
                return n
        return None

    def add_gap(who: str, headline: str, evidence: List[str]):
        out.append({"who": who, "headline": headline, "evidence": evidence})

    if mode != "solo":
        ca = find_closeness(latest_a.get("closeness_space",""))
        cb = find_closeness(latest_b.get("closeness_space",""))
        if ca is not None and cb is not None and abs(ca-cb) >= 4:
            add_gap("pair", "Closeness vs space needs appear far apart",
                    [f"A closeness number: {ca}", f"B closeness number: {cb}"])

    # Values vs boundary mismatch: if one lists "freedom" and the other lists "control"/"structure" (very crude)
    def token_set(t: str):
        import re
        return set(re.findall(r"[a-zA-Z']{4,}", (t or "").lower()))

    if mode != "solo":
        va = token_set(latest_a.get("values_top2","") + " " + latest_a.get("one_boundary",""))
        vb = token_set(latest_b.get("values_top2","") + " " + latest_b.get("one_boundary",""))
        if ("freedom" in va and ("control" in vb or "structure" in vb)) or ("freedom" in vb and ("control" in va or "structure" in va)):
            add_gap("pair", "Freedom vs structure could become a recurring negotiation",
                    ["One side emphasizes freedom; the other emphasizes control/structure (token check)."])

    return out

def compute_deltas_over_time(history_lookup_fn, relationship_id: str, respondent: str, question_ids: List[str], limit: int = 3) -> List[Dict[str, Any]]:
    # Expects a function like db.get_answer_history(relationship_id, respondent, qid, limit)
    deltas: List[Dict[str, Any]] = []
    for qid in question_ids:
        hist = history_lookup_fn(relationship_id, respondent, qid, limit=limit) or []
        if len(hist) >= 2:
            newest = hist[0]["answer_text"] or ""
            prev = hist[1]["answer_text"] or ""
            if newest.strip() != prev.strip():
                deltas.append({
                    "respondent": respondent,
                    "question_id": qid,
                    "from": prev[:240],
                    "to": newest[:240],
                    "timestamps": [hist[1]["created_at"], hist[0]["created_at"]],
                })
    return deltas
