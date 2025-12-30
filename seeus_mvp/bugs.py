# bugs.py
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple


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

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def is_valid_transition(current: str, nxt: str) -> bool:
    if current not in VALID_TRANSITIONS:
        return False
    return nxt == current or nxt in VALID_TRANSITIONS[current]

@dataclass
class Bug:
    id: str
    title: str
    description: str
    reporter: str
    severity: str
    status: str
    assignee: Optional[str]
    resolution_notes: Optional[str]
    created_at: str
    updated_at: str

    @staticmethod
    def new(title: str, description: str, reporter: str, severity: str) -> "Bug":
        if severity not in SEVERITIES:
            severity = "Medium"
        now = utc_now_iso()
        return Bug(
            id=str(uuid.uuid4()),
            title=title.strip()[:200],
            description=description.strip(),
            reporter=reporter.strip()[:200],
            severity=severity,
            status="New",
            assignee=None,
            resolution_notes=None,
            created_at=now,
            updated_at=now,
        )

def _row_to_bug(row: Tuple[Any, ...]) -> Bug:
    return Bug(
        id=row[0],
        title=row[1],
        description=row[2],
        reporter=row[3],
        severity=row[4],
        status=row[5],
        assignee=row[6],
        resolution_notes=row[7],
        created_at=row[8],
        updated_at=row[9],
    )

def create_bugs_table(conn: sqlite3.Connection) -> None:
    """
    Migration-safe: creates the bugs table if it doesn't exist.
    """
    conn.execute(
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bugs_status ON bugs(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bugs_severity ON bugs(severity);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_bugs_updated ON bugs(updated_at);")
    conn.commit()

def save_bug(conn: sqlite3.Connection, bug: Bug) -> None:
    create_bugs_table(conn)
    conn.execute(
        """
        INSERT INTO bugs (
            id, title, description, reporter, severity, status, assignee,
            resolution_notes, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bug.id, bug.title, bug.description, bug.reporter, bug.severity, bug.status,
            bug.assignee, bug.resolution_notes, bug.created_at, bug.updated_at
        ),
    )
    conn.commit()

def get_bug(conn: sqlite3.Connection, bug_id: str) -> Optional[Bug]:
    create_bugs_table(conn)
    cur = conn.execute(
        "SELECT id,title,description,reporter,severity,status,assignee,resolution_notes,created_at,updated_at FROM bugs WHERE id=?",
        (bug_id,),
    )
    row = cur.fetchone()
    return _row_to_bug(row) if row else None

def list_bugs(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    assignee: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> List[Bug]:
    create_bugs_table(conn)
    where = []
    params: List[Any] = []

    if status and status != "All":
        where.append("status = ?")
        params.append(status)

    if severity and severity != "All":
        where.append("severity = ?")
        params.append(severity)

    if assignee and assignee != "All":
        if assignee == "(Unassigned)":
            where.append("(assignee IS NULL OR assignee = '')")
        else:
            where.append("assignee = ?")
            params.append(assignee)

    if search:
        where.append("(title LIKE ? OR description LIKE ? OR reporter LIKE ? OR assignee LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s, s])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT id,title,description,reporter,severity,status,assignee,resolution_notes,created_at,updated_at
        FROM bugs
        {where_sql}
        ORDER BY updated_at DESC
        LIMIT ?
    """
    params.append(limit)

    cur = conn.execute(sql, tuple(params))
    return [_row_to_bug(r) for r in cur.fetchall()]

def update_bug(
    conn: sqlite3.Connection,
    bug_id: str,
    *,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> Bug:
    bug = get_bug(conn, bug_id)
    if not bug:
        raise ValueError("Bug not found")

    if status:
        if status not in BUG_STATUSES:
            raise ValueError("Invalid status")
        if not is_valid_transition(bug.status, status):
            raise ValueError(f"Invalid transition: {bug.status} → {status}")
        bug.status = status

    if assignee is not None:
        bug.assignee = assignee.strip() or None

    if resolution_notes is not None:
        bug.resolution_notes = resolution_notes.strip() or None

    if title is not None:
        bug.title = title.strip()[:200]

    if description is not None:
        bug.description = description.strip()

    bug.updated_at = utc_now_iso()

    create_bugs_table(conn)
    conn.execute(
        """
        UPDATE bugs SET
            title=?,
            description=?,
            reporter=?,
            severity=?,
            status=?,
            assignee=?,
            resolution_notes=?,
            created_at=?,
            updated_at=?
        WHERE id=?
        """,
        (
            bug.title,
            bug.description,
            bug.reporter,
            bug.severity,
            bug.status,
            bug.assignee,
            bug.resolution_notes,
            bug.created_at,
            bug.updated_at,
            bug.id,
        ),
    )
    conn.commit()
    return bug

def bug_metrics(conn: sqlite3.Connection) -> Dict[str, Any]:
    create_bugs_table(conn)
    cur = conn.execute("SELECT status, COUNT(*) FROM bugs GROUP BY status")
    by_status = {k: v for k, v in cur.fetchall()}

    cur = conn.execute("SELECT severity, COUNT(*) FROM bugs GROUP BY severity")
    by_severity = {k: v for k, v in cur.fetchall()}

    cur = conn.execute("""
        SELECT COUNT(*) FROM bugs
        WHERE severity='Critical' AND status NOT IN ('Closed','Rejected')
    """)
    open_critical = cur.fetchone()[0]

    return {
        "by_status": by_status,
        "by_severity": by_severity,
        "open_critical": open_critical,
    }
