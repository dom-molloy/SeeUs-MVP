import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

DB_PATH = Path("seeus.db")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


def init_db():
    with conn() as c:
        c.executescript(
            '''
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
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                relationship_id TEXT,
                mode TEXT,
                started_at TEXT,
                ended_at TEXT
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
                shift_text TEXT,
                metrics_json TEXT         -- {clarity:0-5,cost:0-5,agency:0-5}
            );

            CREATE INDEX IF NOT EXISTS idx_growth_rel ON growth_checkins(relationship_id);
            CREATE INDEX IF NOT EXISTS idx_growth_rel_month ON growth_checkins(relationship_id, month_key);

            -- Optional free-form monthly reflection prompt responses
            CREATE TABLE IF NOT EXISTS growth_reflections (
                reflection_id TEXT PRIMARY KEY,
                relationship_id TEXT,
                respondent TEXT,
                created_at TEXT,
                month_key TEXT,
                prompt_text T_
