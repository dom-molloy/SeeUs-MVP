import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

DB_PATH = Path("seeus.db")


@contextmanager
def conn():
    # Streamlit can hit SQLite from different threads; this avoids common issues.
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


def _split_sql_statements(sql: str) -> list[str]:
    """
    Simple semicolon-based splitter; works well for typical CREATE TABLE/INDEX schemas.
    (Avoids the opaque executescript error inside Streamlit Cloud.)
    """
    parts = [p.strip() for p in sql.split(";")]
    return [p + ";" for p in parts if p]


SCHEMA_SQL = r"""
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    display_name TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS relationships (
    relationship_id TEXT PRIMARY KEY,
    user_a_id TEXT,
    user_b_id TEXT,
    label TEXT,
    created_at TEXT,
    is_archived INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    relationship_id TEXT,
    mode TEXT,
    started_at TEXT,
    ended_at TEXT,
    tone_profile TEXT
);

CREATE TABLE IF NOT EXISTS responses (
    response_id TEXT PRIMARY KEY,
    session_id TEXT,
    relationship_id TEXT,
    respondent TEXT,          -- A|B|solo
    question_id TEXT,
    answer_text TEXT,
    answer_json TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_responses_rel ON responses(relationship_id);
CREATE INDEX IF NOT EXISTS idx_responses_sess ON responses(session_id);
CREATE INDEX IF NOT EXISTS idx_responses_q ON responses(question_id);
CREATE INDEX IF NOT EXISTS idx_responses_rel_resp_q ON responses(relationship_id, respondent, question_id);

-- Stored reports (heuristic/llm/deep) for consistency across sessions
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    relationship_id TEXT,
    report_type TEXT,         -- heuristic|llm|deep
    created_at TEXT,
    content_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_reports_rel ON reports(relationship_id);

-- Growth check-ins (monthly cadence)
CREATE TABLE IF NOT EXISTS growth_checkins (
    checkin_id TEXT PRIMARY KEY,
    relationship_id TEXT,
    mode TEXT,                -- solo|duo
    respondent TEXT,          -- solo|A|B
    created_at TEXT,
    month_key TEXT,           -- YYYY-MM
    pattern_text TEXT,
    cost_text TEXT,
    repair_choice TEXT,
    agency_choice TEXT,
    shift_t_

