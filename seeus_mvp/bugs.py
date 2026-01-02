# seeus_mvp/bugs.py
import json
import uuid
from typing import Any, Dict, List, Optional

from seeus_mvp.db import conn, now_iso


BUG_STATUSES = ["New", "In Progress", "Completed", "Rejected"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]


def init_bugs_table():
    with conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS bugs (
                bug_id TEXT PRIMARY KEY,
                created_at TEXT,
                created_by TEXT,
                title TEXT,
                description TEXT,
                severity TEXT,
                status TEXT,
                assignee TEXT,
                resolution_notes TEXT,
                tags_json TEXT
            );
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bugs_sev ON bugs(severity)")


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
                title.strip(),
                description.strip(),
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
        params.append(assignee.strip() or None)
    if resolution_notes is not None:
        sets.append("resolution_notes=?")
        params.append(resolution_notes.strip() or None)
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
        by_status = {r["status"]: int(r["n"]) for r in rows}

        crit_open = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM bugs
            WHERE severity='Critical' AND status IN ('New','In Progress')
            """
        ).fetchone()

    return {
        "by_status": by_status,
        "open_critical": int(crit_open["n"]) if crit_open else 0,
    }
