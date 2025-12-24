from scoring import overall_score

DIMENSION_ORDER = [
    "values","attachment","conflict","cost","power","stress","load","pattern","future","agency"
]

DIMENSION_LABELS = {
    "values": "Values hierarchy",
    "attachment": "Closeness vs space",
    "conflict": "Repair & conflict",
    "cost": "Cost tolerance",
    "power": "Power & decisions",
    "stress": "Stress behavior",
    "load": "Emotional labor",
    "pattern": "Repeated roles",
    "future": "Future realism",
    "agency": "Agency / choice",
}

def build_headlines(scores):
    items = [(dim, s[0]) for dim, s in scores.items() if s[0] > 0]
    items.sort(key=lambda x: x[1], reverse=True)
    top = items[:3]
    bottom = list(reversed(items[-3:])) if len(items) >= 3 else items[-3:]
    return {"top": top, "bottom": bottom, "overall": overall_score(scores)}
