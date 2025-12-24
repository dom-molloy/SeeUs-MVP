# Canonical question bank for SeeUs (Deep-Research-driven)
# Keep IDs stable.

def p(default, gentle=None, clear=None, sharp=None):
    return {
        "default": default,
        "gentle": gentle or default,
        "clear": clear or default,
        "sharp": sharp or default,
    }

QUESTIONS = [
    # ---- Core (Primary) ----
    {
        "id": "values_hierarchy",
        "dimension": "values",
        "primary": True,
        "prompt": p(
            "When two values conflict in real life (e.g., freedom vs closeness, ambition vs presence), which one usually wins in your actual decisions?",
            gentle="When two important values bump into each other (like freedom vs closeness), which one tends to win in your real decisions?",
            clear="When values conflict (freedom vs closeness, ambition vs presence), which one wins in your actual decisions?",
            sharp="When values conflict, which one wins in your behavior—no matter what you say you want?",
        ),
        "signals": ["values_priority", "sacrifice_direction"],
        "numeric": False,
        "branch": "values_example_followup",
    },
    {
        "id": "cost_tolerance",
        "dimension": "cost",
        "primary": True,
        "prompt": p(
            "What ongoing discomfort have you historically accepted to stay connected to someone?",
            gentle="What discomfort have you tended to carry in order to stay close to someone?",
            clear="What discomfort have you historically tolerated to stay connected?",
            sharp="What pain have you accepted to keep a relationship alive?",
        ),
        "signals": ["cost_normalization", "overfunctioning", "self_abandonment_risk"],
        "numeric": False,
        "branch": "cost_line_followup",
    },
    {
        "id": "repair_capacity",
        "dimension": "conflict",
        "primary": True,
        "prompt": p(
            "After conflict, who usually moves first to repair—and what happens if they don’t?",
            gentle="After conflict, who usually reaches out first to repair—and what happens if they don’t?",
            clear="After conflict, who initiates repair—and what happens if they don’t?",
            sharp="After conflict, who does the repair work—and what happens if they stop?",
        ),
        "signals": ["repair_initiation", "repair_risk", "silence_cost"],
        "numeric": False,
        "branch": "repair_risk_followup",
    },
    {
        "id": "emotional_labor",
        "dimension": "load",
        "primary": True,
        "prompt": p(
            "In relationships, what do you notice yourself tracking or managing that your partner often doesn’t?",
            gentle="In relationships, what do you find yourself quietly tracking or managing that your partner may not notice?",
            clear="What do you track/manage that your partner often doesn’t?",
            sharp="What invisible work do you do that your partner benefits from but doesn’t carry?",
        ),
        "signals": ["load_imbalance", "mental_overhead"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "closeness_numeric",
        "dimension": "attachment",
        "primary": True,
        "prompt": p(
            "On a 0–10 scale, how much day-to-day closeness do you want? What does “too much” look like in practice?",
            gentle="On a 0–10 scale, how much day-to-day closeness feels good? And what does “too much” look like for you?",
            clear="0–10: desired day-to-day closeness. What does “too much” look like?",
            sharp="Give a number (0–10) for closeness you want—then describe what makes it feel suffocating.",
        ),
        "signals": ["closeness_need", "space_need"],
        "numeric": True,
        "branch": "closeness_gap_followup",
    },
    # --- Mirror Moment happens after this question (Q5) ---
    {
        "id": "power_decisions",
        "dimension": "power",
        "primary": True,
        "prompt": p(
            "When there’s a meaningful disagreement, how is the final decision usually made?",
            gentle="When you disagree about something that matters, how do decisions usually get made?",
            clear="In meaningful disagreements, how is the final decision made?",
            sharp="When you disagree, who actually wins—and how does that happen?",
        ),
        "signals": ["power_symmetry", "avoidance_masking"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "stress_behavior",
        "dimension": "stress",
        "primary": True,
        "prompt": p(
            "Under prolonged stress (money, health, work), what do you tend to need more of—and what do you tend to withdraw from?",
            gentle="Under prolonged stress, what do you need more of—and what do you pull away from?",
            clear="Under prolonged stress, what do you need more of—and what do you withdraw from?",
            sharp="Under stress, what do you demand more of—and what do you stop doing?",
        ),
        "signals": ["stress_needs", "stress_withdrawal"],
        "numeric": False,
        "branch": "stress_duration_followup",
    },
    {
        "id": "pattern_role",
        "dimension": "pattern",
        "primary": True,
        "prompt": p(
            "What familiar role do you notice yourself slipping into across different relationships?",
            gentle="Across relationships, what role do you notice yourself falling into?",
            clear="What role do you tend to repeat across relationships?",
            sharp="What part do you keep playing—over and over?",
        ),
        "signals": ["pattern_replay", "identity_trap"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "future_self",
        "dimension": "future",
        "primary": True,
        "prompt": p(
            "Imagine this relationship exactly as it is today, three years from now. What feels nourishing? What feels heavy?",
            gentle="Imagine this stays exactly the same for three years. What would feel nourishing—and what would feel heavy?",
            clear="Same as today for 3 years: what’s nourishing vs heavy?",
            sharp="Three years of this unchanged: what keeps you—and what breaks you?",
        ),
        "signals": ["time_cost_awareness", "fantasy_gap"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "agency_choice",
        "dimension": "agency",
        "primary": True,
        "prompt": p(
            "If nothing changed, would you still actively choose this relationship?",
            gentle="If nothing changed, would you still choose this relationship?",
            clear="If nothing changes, do you still choose this?",
            sharp="If nothing changes, are you staying by choice—or by attachment?",
        ),
        "signals": ["agency_clarity", "ambivalence"],
        "numeric": False,
        "branch": "agency_clarify_followup",
    },

    # ---- Branch (Non-primary) ----
    {
        "id": "values_example_followup",
        "dimension": "values",
        "primary": False,
        "prompt": p("Can you share one recent moment where those values conflicted, and what you actually did?"),
        "signals": ["values_in_action"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "cost_line_followup",
        "dimension": "cost",
        "primary": False,
        "prompt": p("Where is your line? What discomfort is no longer acceptable for you?"),
        "signals": ["boundary_line"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "repair_risk_followup",
        "dimension": "conflict",
        "primary": False,
        "prompt": p("What feels risky about being the one who initiates repair?"),
        "signals": ["repair_fear", "vulnerability_cost"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "closeness_gap_followup",
        "dimension": "attachment",
        "primary": False,
        "prompt": p("When closeness/space needs differ, what tends to happen between you? How do you negotiate it?"),
        "signals": ["calibration_skill"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "stress_duration_followup",
        "dimension": "stress",
        "primary": False,
        "prompt": p("What tends to happen between you when stress lasts longer than expected (weeks/months)?"),
        "signals": ["stress_loop"],
        "numeric": False,
        "branch": None,
    },
    {
        "id": "agency_clarify_followup",
        "dimension": "agency",
        "primary": False,
        "prompt": p("What would need to change for this to feel like a clear yes?"),
        "signals": ["change_conditions"],
        "numeric": False,
        "branch": None,
    },

    # ---- Meta (system) ----
    {
        "id": "mirror_correction",
        "dimension": "meta",
        "primary": False,
        "prompt": p("If I missed it, what should I understand differently? (Optional)"),
        "signals": ["calibration_feedback"],
        "numeric": False,
        "branch": None,
    },
]

PRIMARY_IDS = [q["id"] for q in QUESTIONS if q.get("primary")]
QUESTION_BY_ID = {q["id"]: q for q in QUESTIONS}
