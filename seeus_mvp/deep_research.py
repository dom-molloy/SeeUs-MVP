import os
import json
from typing import Dict, Any, List, Optional, Tuple
from prompts import SYSTEM

DEEP_RESEARCH_SYSTEM = SYSTEM + """
You produce a 'Relational Dynamics Brief' grounded ONLY in the provided answers and computed scores.
Do NOT diagnose, label attachment styles, or speculate about mental health, trauma, or childhood.
Do NOT claim to have browsed the web.
Use careful language: 'tends to', 'often', 'can', 'may'.
If information is missing, say what is missing and ask targeted follow-ups.
Output must be valid JSON only.
"""

DEEP_RESEARCH_OUTPUT_SPEC = """
Return JSON with this schema:
{
  "title": "Relational Dynamics Brief",
  "observed_patterns": [ {"headline": str, "evidence": [str], "why_it_matters": str} ],
  "what_tends_to_happen": [ {"headline": str, "mechanism": str, "conditions": str} ],
  "early_wins": [str],
  "likely_failure_modes": [ {"name": str, "how_it_starts": str, "how_it_ends": str, "risk_level": "Low|Medium|High"} ],
  "leverage_points": [ {"action": str, "why": str, "how_to_try": str} ],
  "stay_change_leave_lens": {
     "stay_as_is": str,
     "change_one_thing": str,
     "if_nothing_changes": str
  },
  "follow_up_questions": [str],
  "limits": [str]
}
"""

DEEP_RESEARCH_USER_PROMPT = """
You are given:
- relationship_mode: {mode}
- dimension_scores: {scores_json}
- key_quotes: {quotes_json}
- contradictions: {contradictions_json}
- deltas_over_time: {deltas_json}

Task:
Write a deep, non-clinical research-style brief that:
1) Anchors claims in evidence from key_quotes + scores (include short evidence bullets).
2) Separates misalignment from cost (name costs neutrally).
3) Identifies likely failure modes (adult framing, not 'red flags').
4) Provides 2–4 leverage points as experiments/rituals.
5) Ends with a Stay/Change/Leave lens (no telling them what to do).

{output_spec}
"""

def _get_client():
    try:
        from openai import OpenAI
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception:
        return None

def _chat(client, model: str, system: str, user: str) -> str:
    if client is not None:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.2,
        )
        return resp.choices[0].message.content
    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    resp = openai.ChatCompletion.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=0.2,
    )
    return resp["choices"][0]["message"]["content"]

def run_deep_research(
    mode: str,
    dimension_scores: List[Dict[str, Any]],
    key_quotes: Dict[str, List[str]],
    contradictions: List[Dict[str, Any]],
    deltas_over_time: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
) -> Dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")

    client = _get_client()
    prompt = DEEP_RESEARCH_USER_PROMPT.format(
        mode=mode,
        scores_json=json.dumps(dimension_scores, ensure_ascii=False),
        quotes_json=json.dumps(key_quotes, ensure_ascii=False),
        contradictions_json=json.dumps(contradictions, ensure_ascii=False),
        deltas_json=json.dumps(deltas_over_time, ensure_ascii=False),
        output_spec=DEEP_RESEARCH_OUTPUT_SPEC.strip()
    )
    raw = _chat(client, model=model, system=DEEP_RESEARCH_SYSTEM, user=prompt)

    try:
        return json.loads(raw)
    except Exception:
        s = raw.find("{")
        e = raw.rfind("}")
        if s != -1 and e != -1 and e > s:
            return json.loads(raw[s:e+1])
        raise
