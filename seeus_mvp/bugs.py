# seeus_mvp/bugs.py
import json
import uuid
from typing import Any, Dict, List, Optional

from seeus_mvp.db import conn, now_iso

BUG_STATUSES = ["New", "In Progress", "Completed", "Rejected"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]

# Canonical schema for bugs table
_BUGS_COLUMNS = [
    ("bug_id", "TEXT PRIMARY KEY"),
    ("created_at", "TEXT"),
    ("created_by", "TEXT"),
    ("title", "TEXT"),
    ("description", "TEXT"),
    ("severity", "TEXT"),
    ("status", "TEXT"),
    ("assignee", "TEXT"),
    ("resolution_notes", "TEXT"),
    ("tags_json", "TEXT"),
]


def _table_exists(c, name: str) -> bool:
    row = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return bool(row)


def _get_columns(c, table: str) -> List[str]:
    rows = c.execute(f"PRAGMA table_info({table})").fetchall()
    # sqlite3.Row supports dict-like access if row_factory is set; otherwise use index
    cols = []
    for r in rows:
        try:
            cols.append(r["name"])
        except Exception:
            cols.append(r[1])
    return cols


def init_bugs_table():
    """
    Ensures the bugs table exists with the expected schema.

    Migration behavior (keeps data when possible):
      - If 'bugs' doesn't exist: create it
      - If 'bugs' exists but schema differs: create bugs_new, copy overlapping columns,
        drop old bugs, rename bugs_new -> bugs
    """
    with conn() as c:
        # Create if missing
        if not _table_exists(c, "bugs"):
            c.execute(
                f"""
                CREATE TABLE IF NOT EXISTS bugs (
                    {", ".join([f"{n} {t}" for n, t in _BUGS_COLUMNS])}
                );
                """
            )
        else:
            existing_cols = set(_get_columns(c, "bugs"))
            expected_cols = [n for n, _ in _BUGS_COLUMNS]
            expected_set = set(expected_cols)

            # If mismatch, migrate
            if existing_cols != expected_set:
                c.execute("DROP TABLE IF EXISTS bugs_new;")
                c.execute(
                    f"""
                    CREATE TABLE bugs_new (
                        {", ".join([f"{n} {t}" for n, t in _BUGS_COLUMNS])}
                    );
                    """
                )

                overlap = [col for col in expected_cols if col in existing_cols]
                if overlap:
                    cols_csv = ", ".join(overlap)
                    c.execute(
                        f"""
                        INSERT INTO bugs_new ({cols_csv})
                        SELECT {cols_csv}
                        FROM bugs;
                        """
                    )

                c.execute("DROP TABLE bugs;")
                c.execute("ALTER TABLE bugs_new RENAME TO bugs;")

        # Indexes (safe to run repeatedly)
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_sev ON bugs(severity);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_created_at ON bugs(created_at);")


def create_bug(
    title: str,
    description: str,
    created_by: str,
    severity: str = "Medium",
    tags: Optional[List[str]] = None,
) -> str:
    bug_id = str(uuid.uuid4())
    with conn() as c:
        c.execute(
            """
            INSERT INTO bugs (
                bug_id, created_at, created_by, title, description,
                severity, status, assignee, resolution_notes, tags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bug_id,
                now_iso(),
                created_by,
                (title or "").strip(),
                (description or "").strip(),
                severity,
                "New",
                None,
                None,
                json.dumps(tags or []),
            ),
        )
    return bug_id


def list_bugs(status: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    q = "SELECT * FROM bugs"
    clauses = []
    params = []

    if status and status != "All":
        clauses.append("status=?")
        params.append(status)
    if severity and severity != "All":
        clauses.append("severity=?")
        params.append(severity)

    if clauses:
        q += " WHERE " + " AND ".join(clauses)
    q += " ORDER BY created_at DESC"

    with conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def get_bug(bug_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute("SELECT * FROM bugs WHERE bug_id=?", (bug_id,)).fetchone()
        return dict(row) if row else None


def update_bug(
    bug_id: str,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    severity: Optional[str] = None,
):
    sets = []
    params = []

    if status is not None:
        sets.append("status=?")
        params.append(status)
    if assignee is not None:
        sets.append("assignee=?")
        params.append((assignee or "").strip() or None)
    if resolution_notes is not None:
        sets.append("resolution_notes=?")
        params.append((resolution_notes or "").strip() or None)
    if severity is not None:
        sets.append("severity=?")
        params.append(severity)

    if not sets:
        return

    params.append(bug_id)
    with conn() as c:
        c.execute(f"UPDATE bugs SET {', '.join(sets)} WHERE bug_id=?", params)


def bug_metrics() -> Dict[str, Any]:
    with conn() as c:
        rows = c.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM bugs
            GROUP BY status
            """
        ).fetchall()
        by_status = {}
        for r in rows:
            try:
                by_status[r["status"]] = int(r["n"])
            except Exception:
                by_status[r[0]] = int(r[1])

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

    return {
        "by_status": by_status,
        "open_critical": open_critical,
    }
