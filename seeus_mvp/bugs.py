# seeus_mvp/bugs.py
import uuid
from typing import Any, Dict, List, Optional

from seeus_mvp.db import conn, now_iso

BUG_STATUSES = ["New", "In Progress", "Completed", "Rejected"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]


def _table_exists(c, name: str) -> bool:
    row = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _get_columns(c, table: str) -> List[str]:
    rows = c.execute(f"PRAGMA table_info({table})").fetchall()
    cols: List[str] = []
    for r in rows:
        try:
            cols.append(r["name"])
        except Exception:
            cols.append(r[1])
    return cols


def init_bugs_table():
    """
    Ensures the bugs table exists and matches the schema defined in db.py.

    Canonical schema (aligned to db.py):
      - id (TEXT PRIMARY KEY)
      - title, description (TEXT NOT NULL)
      - reporter (TEXT)
      - severity (TEXT)
      - status (TEXT)
      - assignee (TEXT)
      - resolution_notes (TEXT)
      - created_at (TEXT)
      - updated_at (TEXT)

    Migration behavior:
      - If bugs missing: create it
      - If bugs exists with old schema (bug_id/created_by/tags_json): migrate data into canonical schema
      - If bugs exists missing updated_at: add column
    """
    with conn() as c:
        if not _table_exists(c, "bugs"):
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS bugs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    reporter TEXT,
                    severity TEXT,
                    status TEXT,
                    assignee TEXT,
                    resolution_notes TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                """
            )
        else:
            cols = set(_get_columns(c, "bugs"))

            # --- Migrate from old schema used by previous bugs.py (bug_id/created_by/tags_json) ---
            old_schema = {"bug_id", "created_by", "tags_json"}
            canonical_min = {"id", "title", "description", "created_at"}  # minimal proof of new schema

            if old_schema.intersection(cols) and not canonical_min.issubset(cols):
                # Create canonical table and map columns across
                c.execute("DROP TABLE IF EXISTS bugs_new;")
                c.execute(
                    """
                    CREATE TABLE bugs_new (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL,
                        reporter TEXT,
                        severity TEXT,
                        status TEXT,
                        assignee TEXT,
                        resolution_notes TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    );
                    """
                )

                # Copy + map overlapping fields:
                # old.bug_id -> new.id
                # old.created_by -> new.reporter
                # old.created_at -> new.created_at
                # old.title/description/severity/status/assignee/resolution_notes -> same if present
                # updated_at -> null (or created_at)
                copy_sql = """
                    INSERT INTO bugs_new (
                        id, title, description, reporter, severity, status,
                        assignee, resolution_notes, created_at, updated_at
                    )
                    SELECT
                        COALESCE(bug_id, id),
                        COALESCE(title, '(missing title)'),
                        COALESCE(description, '(missing description)'),
                        COALESCE(created_by, reporter),
                        COALESCE(severity, 'Medium'),
                        COALESCE(status, 'New'),
                        assignee,
                        resolution_notes,
                        created_at,
                        COALESCE(updated_at, created_at)
                    FROM bugs;
                """
                c.execute(copy_sql)

                c.execute("DROP TABLE bugs;")
                c.execute("ALTER TABLE bugs_new RENAME TO bugs;")

            # --- Ensure updated_at exists on canonical table ---
            cols2 = set(_get_columns(c, "bugs"))
            if "updated_at" not in cols2:
                c.execute("ALTER TABLE bugs ADD COLUMN updated_at TEXT")

            # Also ensure created_at exists (defensive)
            if "created_at" not in cols2:
                c.execute("ALTER TABLE bugs ADD COLUMN created_at TEXT")

        # Indexes (safe to run repeatedly)
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_severity ON bugs(severity);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_updated ON bugs(updated_at);")


def create_bug(
    title: str,
    description: str,
    reporter: str,
    severity: str = "Medium",
) -> str:
    bug_id = str(uuid.uuid4())
    created = now_iso()
    sev = severity if severity in SEVERITIES else "Medium"
    with conn() as c:
        c.execute(
            """
            INSERT INTO bugs (
                id, title, description, reporter, severity, status,
                assignee, resolution_notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bug_id,
                (title or "").strip(),
                (description or "").strip(),
                (reporter or "").strip() or None,
                sev,
                "New",
                None,
                None,
                created,
                created,
            ),
        )
    return bug_id


def list_bugs(status: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    q = "SELECT * FROM bugs"
    clauses = []
    params: List[Any] = []

    if status:
        clauses.append("status=?")
        params.append(status)
    if severity:
        clauses.append("severity=?")
        params.append(severity)

    if clauses:
        q += " WHERE " + " AND ".join(clauses)

    # Most recently updated first
    q += " ORDER BY COALESCE(updated_at, created_at) DESC"

    with conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def get_bug(bug_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute("SELECT * FROM bugs WHERE id=?", (bug_id,)).fetchone()
        return dict(row) if row else None


def update_bug(
    bug_id: str,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    severity: Optional[str] = None,
):
    sets = []
    params: List[Any] = []

    if status is not None:
        sets.append("status=?")
        params.append(status if status in BUG_STATUSES else status)
    if assignee is not None:
        sets.append("assignee=?")
        params.append((assignee or "").strip() or None)
    if resolution_notes is not None:
        sets.append("resolution_notes=?")
        params.append((resolution_notes or "").strip() or None)
    if severity is not None:
        sev = severity if severity in SEVERITIES else severity
        sets.append("severity=?")
        params.append(sev)

    if not sets:
        return

    # Always touch updated_at on updates
    sets.append("updated_at=?")
    params.append(now_iso())

    params.append(bug_id)
    with conn() as c:
        c.execute(f"UPDATE bugs SET {', '.join(sets)} WHERE id=?", params)


def bug_metrics() -> Dict[str, Any]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM bugs
            GROUP BY status
            """
        ).fetchall()

        by_status: Dict[str, int] = {}
        for r in rows:
            try:
                by_status[str(r["status"])] = int(r["n"])
            except Exception:
                by_status[str(r[0])] = int(r[1])

        crit_open = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM bugs
            WHERE severity='Critical' AND status IN ('New','In Progress')
            """
        ).fetchone()

    try:
        open_critical = int(crit_open["n"]) if crit_open else 0
    except Exception:
        open_critical = int(crit_open[0]) if crit_open else 0

    return {"by_status": by_status, "open_critical": open_critical}
