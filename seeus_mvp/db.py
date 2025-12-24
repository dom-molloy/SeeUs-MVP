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

            -- Invite links for Person B (or A) to fill a relationship assessment

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
                respondent TEXT,          -- Solo|A|B
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
                prompt_text TEXT,
                response_text TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_reflect_rel_month ON growth_reflections(relationship_id, month_key);
CREATE TABLE IF NOT EXISTS invites (
                token TEXT PRIMARY KEY,
                relationship_id TEXT,
                respondent TEXT,          -- A|B|solo
                created_at TEXT,
                used_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_invites_rel ON invites(relationship_id);
            '''
        )

        # lightweight migration(s)
        cols = [r["name"] for r in c.execute("PRAGMA table_info(sessions)").fetchall()]
        if "tone_profile" not in cols:
            c.execute("ALTER TABLE sessions ADD COLUMN tone_profile TEXT")

def upsert_user(user_id, display_name):
    with conn() as c:
        c.execute(
            """
            INSERT INTO users(user_id, display_name, created_at)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name
            """,
            (user_id, display_name, now_iso()),
        )

def create_relationship(relationship_id, user_a_id, user_b_id, label):
    with conn() as c:
        c.execute(
            """
            INSERT INTO relationships(relationship_id, user_a_id, user_b_id, label, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (relationship_id, user_a_id, user_b_id, label, now_iso()),
        )

def list_relationships():
    with conn() as c:
        return c.execute("SELECT * FROM relationships ORDER BY created_at DESC").fetchall()

def get_relationship(relationship_id):
    with conn() as c:
        return c.execute("SELECT * FROM relationships WHERE relationship_id=?", (relationship_id,)).fetchone()

def create_session(session_id, relationship_id, mode, tone_profile=None):
    with conn() as c:
        c.execute(
            """
            INSERT INTO sessions(session_id, relationship_id, mode, tone_profile, started_at, ended_at)
            VALUES(?, ?, ?, ?, ?, NULL)
            """,
            (session_id, relationship_id, mode, tone_profile, now_iso()),
        )

def get_open_session(relationship_id):
    with conn() as c:
        return c.execute(
            """
            SELECT * FROM sessions
            WHERE relationship_id=? AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (relationship_id,),
        ).fetchone()

def end_session(session_id):
    with conn() as c:
        c.execute("UPDATE sessions SET ended_at=? WHERE session_id=?", (now_iso(), session_id))

def save_response(response_id, session_id, relationship_id, respondent, question_id, answer_text, answer_json=None):
    with conn() as c:
        c.execute(
            """
            INSERT INTO responses(response_id, session_id, relationship_id, respondent, question_id, answer_text, answer_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (response_id, session_id, relationship_id, respondent, question_id, answer_text, answer_json, now_iso()),
        )

def get_answers_for_session(session_id):
    with conn() as c:
        return c.execute(
            """
            SELECT * FROM responses
            WHERE session_id=?
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()

def get_last_answers(relationship_id, respondent=None, limit=50):
    with conn() as c:
        if respondent:
            return c.execute(
                """
                SELECT question_id, answer_text, created_at
                FROM responses
                WHERE relationship_id=? AND respondent=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (relationship_id, respondent, limit),
            ).fetchall()
        return c.execute(
            """
            SELECT question_id, answer_text, created_at
            FROM responses
            WHERE relationship_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (relationship_id, limit),
        ).fetchall()

def get_answer_history(relationship_id, respondent, question_id, limit=5):
    with conn() as c:
        return c.execute(
            """
            SELECT answer_text, created_at
            FROM responses
            WHERE relationship_id=? AND respondent=? AND question_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (relationship_id, respondent, question_id, limit),
        ).fetchall()

# --- Invites ---
def create_invite(token, relationship_id, respondent):
    with conn() as c:
        c.execute(
            """
            INSERT INTO invites(token, relationship_id, respondent, created_at, used_at)
            VALUES(?, ?, ?, ?, ?, NULL)
            """,
            (token, relationship_id, respondent, now_iso()),
        )

def get_invite(token):
    with conn() as c:
        return c.execute("SELECT * FROM invites WHERE token=?", (token,)).fetchone()

def mark_invite_used(token):
    with conn() as c:
        c.execute("UPDATE invites SET used_at=? WHERE token=? AND used_at IS NULL", (now_iso(), token))


# --- Reports ---
def save_report(report_id, relationship_id, report_type, content_json):
    with conn() as c:
        c.execute(
            """
            INSERT INTO reports(report_id, relationship_id, report_type, created_at, content_json)
            VALUES(?, ?, ?, ?, ?)
            """,
            (report_id, relationship_id, report_type, now_iso(), content_json),
        )

def get_latest_report(relationship_id, report_type=None):
    with conn() as c:
        if report_type:
            return c.execute(
                """
                SELECT * FROM reports
                WHERE relationship_id=? AND report_type=?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (relationship_id, report_type),
            ).fetchone()
        return c.execute(
            """
            SELECT * FROM reports
            WHERE relationship_id=?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (relationship_id,),
        ).fetchone()

# --- Growth ---
def save_growth_checkin(checkin_id, relationship_id, mode, respondent, month_key, pattern_text, cost_text, repair_choice, agency_choice, shift_text, metrics_json):
    with conn() as c:
        c.execute(
            """
            INSERT INTO growth_checkins(
                checkin_id, relationship_id, mode, respondent, created_at, month_key,
                pattern_text, cost_text, repair_choice, agency_choice, shift_text, metrics_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkin_id, relationship_id, mode, respondent, now_iso(), month_key,
                pattern_text, cost_text, repair_choice, agency_choice, shift_text, metrics_json
            )
        )

def list_growth_checkins(relationship_id, respondent=None, limit=50):
    with conn() as c:
        if respondent:
            rows = c.execute(
                """
                SELECT * FROM growth_checkins
                WHERE relationship_id=? AND respondent=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (relationship_id, respondent, limit),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT * FROM growth_checkins
                WHERE relationship_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (relationship_id, limit),
            ).fetchall()
    return rows

def get_latest_growth_checkin(relationship_id, respondent=None):
    rows = list_growth_checkins(relationship_id, respondent=respondent, limit=1)
    return rows[0] if rows else None

def save_growth_reflection(reflection_id, relationship_id, respondent, month_key, prompt_text, response_text):
    with conn() as c:
        c.execute(
            """
            INSERT INTO growth_reflections(reflection_id, relationship_id, respondent, created_at, month_key, prompt_text, response_text)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (reflection_id, relationship_id, respondent, now_iso(), month_key, prompt_text, response_text),
        )

def list_growth_reflections(relationship_id, respondent=None, limit=50):
    with conn() as c:
        if respondent:
            return c.execute(
                """
                SELECT * FROM growth_reflections
                WHERE relationship_id=? AND respondent=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (relationship_id, respondent, limit),
            ).fetchall()
        return c.execute(
            """
            SELECT * FROM growth_reflections
            WHERE relationship_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (relationship_id, limit),
        ).fetchall()
