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
    Canonical schema aligned to db.py:
      id (TEXT PK)
      bug_no (INTEGER)
      title/description
      reporter/severity/status/assignee/resolution_notes
      created_at/updated_at
    """
    with conn() as c:
        if not _table_exists(c, "bugs"):
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS bugs (
                    id TEXT PRIMARY KEY,
                    bug_no INTEGER,
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

        cols = set(_get_columns(c, "bugs"))

        # Ensure columns exist (defensive migrations)
        if "bug_no" not in cols:
            c.execute("ALTER TABLE bugs ADD COLUMN bug_no INTEGER")
            c.execute("UPDATE bugs SET bug_no = COALESCE(bug_no, rowid) WHERE bug_no IS NULL")

        if "updated_at" not in cols:
            c.execute("ALTER TABLE bugs ADD COLUMN updated_at TEXT")

        # Indexes
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_severity ON bugs(severity);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_updated ON bugs(updated_at);")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bugs_bug_no ON bugs(bug_no);")


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
        row = c.execute("SELECT COALESCE(MAX(bug_no), 0) + 1 AS next_no FROM bugs").fetchone()
        next_no = int(row["next_no"]) if row and row["next_no"] is not None else 1

        c.execute(
            """
            INSERT INTO bugs (
                id, bug_no, title, description, reporter, severity, status,
                assignee, resolution_notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bug_id,
                next_no,
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

    q += " ORDER BY COALESCE(bug_no, 999999999) DESC, COALESCE(updated_at, created_at) DESC"

    with conn() as c:
        return [dict(r) for r in c.execute(q, params).fetchall()]


def get_bug(bug_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute("SELECT * FROM bugs WHERE id=?", (bug_id,)).fetchone()
        return dict(row) if row else None


def update_bug(
    bug_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    severity: Optional[str] = None,
):
    sets = []
    params: List[Any] = []

    if title is not None:
        sets.append("title=?")
        params.append((title or "").strip())

    if description is not None:
        sets.append("description=?")
        params.append((description or "").strip())

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

    return {"by_status": by_status, "open_critical": open_critical}
