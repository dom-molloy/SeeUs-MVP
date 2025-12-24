import os
import json
from typing import Dict, Any, List, Tuple, Optional
from prompts import SYSTEM, make_dimension_prompt
from questions import QUESTIONS

# --- OpenAI client wrapper (supports modern python SDK) ---
def _get_client():
    try:
        from openai import OpenAI  # new SDK (>=1.0)
        return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception:
        return None

def _chat_completion(client, model: str, system: str, user: str) -> str:
    # New SDK path
    if client is not None:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content

    # Legacy fallback (best-effort)
    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    resp = openai.ChatCompletion.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    return resp["choices"][0]["message"]["content"]

def _group_inputs_by_dimension(answers: Dict[str, str]) -> Dict[str, str]:
    dim_text: Dict[str, List[str]] = {}
    q_lookup = {q["id"]: q for q in QUESTIONS}
    for qid, ans in answers.items():
        q = q_lookup.get(qid)
        if not q:
            continue
        dim = q["dimension"]
        dim_text.setdefault(dim, []).append(f"- {q['text']}\n  Answer: {ans}" )
    return {dim: "\n".join(lines) for dim, lines in dim_text.items()}

def score_duo_llm(
    answers_a: Dict[str, str],
    answers_b: Dict[str, str],
    model: str = "gpt-4o-mini"
) -> List[Dict[str, Any]]:
    """Return list of per-dimension dicts: {dimension, score(0-10), confidence, rationale, prompts_next}."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")

    client = _get_client()
    a_by_dim = _group_inputs_by_dimension(answers_a)
    b_by_dim = _group_inputs_by_dimension(answers_b)

    all_dims = sorted(set(a_by_dim.keys()) | set(b_by_dim.keys()))
    out: List[Dict[str, Any]] = []

    for dim in all_dims:
        prompt = make_dimension_prompt(dim, a_by_dim.get(dim, "(none)"), b_by_dim.get(dim, "(none)"))
        raw = _chat_completion(client, model=model, system=SYSTEM, user=prompt)

        # Parse JSON robustly
        try:
            data = json.loads(raw)
        except Exception:
            # attempt to extract JSON block
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(raw[start:end+1])
            else:
                raise

        # Normalize
        data["dimension"] = data.get("dimension") or dim
        try:
            data["score"] = float(data.get("score"))
        except Exception:
            data["score"] = 0.0
        out.append(data)

    return out

def overall_from_llm(dim_scores: List[Dict[str, Any]]) -> float:
    vals = [float(d.get("score", 0)) for d in dim_scores if d.get("score") is not None]
    vals = [v for v in vals if v > 0]
    return round(sum(vals)/len(vals), 1) if vals else 0.0
