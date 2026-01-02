# bugs.py
import uuid
from typing import Optional, List, Any, Dict
from db import conn, now_iso

BUG_STATUSES = ["New", "In Progress", "Fixed", "Verified", "Closed", "Rejected"]
SEVERITIES = ["Low", "Medium", "High", "Critical"]

VALID_TRANSITIONS = {
    "New": ["In Progress", "Rejected"],
    "In Progress": ["Fixed", "Rejected"],
    "Fixed": ["Verified"],
    "Verified": ["Closed"],
    "Closed": [],
    "Rejected": [],
}


def is_valid_transition(current: str, nxt: str) -> bool:
    return nxt == current or nxt in VALID_TRANSITIONS.get(current, [])


def create_bug(title: str, description: str, reporter: str, severity: str = "Medium") -> str:
    bug_id = str(uuid.uuid4())
    if severity not in SEVERITIES:
        severity = "Medium"

    with conn() as c:
        c.execute(
            """
            INSERT INTO bugs (
                id, title, description, reporter, severity, status,
                assignee, resolution_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bug_id,
                (title or "").strip()[:200],
                (description or "").strip(),
                (reporter or "unknown").strip()[:200],
                severity,
                "New",
                None,
                None,
                now_iso(),
                now_iso(),
            ),
        )
    return bug_id


def list_bugs(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    assignee: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
):
    where = []
    params: List[Any] = []

    if status and status != "All":
        where.append("status=?")
        params.append(status)

    if severity and severity != "All":
        where.append("severity=?")
        params.append(severity)

    if assignee and assignee != "All":
        if assignee == "(Unassigned)":
            where.append("(assignee IS NULL OR assignee='')")
        else:
            where.append("assignee=?")
            params.append(assignee)

    if search:
        s = f"%{search}%"
        where.append("(title LIKE ? OR description LIKE ? OR reporter LIKE ? OR assignee LIKE ?)")
        params.extend([s, s, s, s])

    where_sql = "WHERE " + " AND ".join(where) if where else ""
    sql = f"SELECT * FROM bugs {where_sql} ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    with conn() as c:
        return c.execute(sql, tuple(params)).fetchall()


def get_bug(bug_id: str):
    with conn() as c:
        return c.execute("SELECT * FROM bugs WHERE id=?", (bug_id,)).fetchone()


def update_bug(
    bug_id: str,
    *,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    resolution_notes: Optional[str] = None,
):
    bug = get_bug(bug_id)
    if not bug:
        raise ValueError("Bug not found")

    if status:
        if status not in BUG_STATUSES:
            raise ValueError("Invalid status")
        if not is_valid_transition(bug["status"], status):
            raise ValueError(f"Invalid transition: {bug['status']} → {status}")

    fields = []
    params: List[Any] = []

    if status is not None:
        fields.append("status=?")
        params.append(status)

    if assignee is not None:
        fields.append("assignee=?")
        params.append(assignee.strip() or None)

    if resolution_notes is not None:
        fields.append("resolution_notes=?")
        params.append(resolution_notes.strip() or None)

    fields.append("updated_at=?")
    params.append(now_iso())

    params.append(bug_id)

    with conn() as c:
        c.execute(f"UPDATE bugs SET {', '.join(fields)} WHERE id=?", tuple(params))


def bug_metrics() -> Dict[str, Any]:
    with conn() as c:
        by_status = {
            r["status"]: r["n"]
            for r in c.execute("SELECT status, COUNT(*) AS n FROM bugs GROUP BY status").fetchall()
        }

        by_severity = {
            r["severity"]: r["n"]
            for r in c.execute("SELECT severity, COUNT(*) AS n FROM bugs GROUP BY severity").fetchall()
        }

        open_critical = c.execute(
            "SELECT COUNT(*) AS n FROM bugs WHERE severity='Critical' AND status NOT IN ('Closed','Rejected')"
        ).fetchone()["n"]

    return {"by_status": by_status, "by_severity": by_severity, "open_critical": open_critical}
