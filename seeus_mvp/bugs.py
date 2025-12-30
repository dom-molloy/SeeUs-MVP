from datetime import datetime
import uuid

BUG_STATUSES = [
    "New",
    "In Progress",
    "Fixed",
    "Verified",
    "Closed",
    "Rejected"
]

def create_bug(title, description, reporter, severity):
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "reporter": reporter,
        "severity": severity,   # Low | Medium | High | Critical
        "status": "New",
        "assignee": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "resolution_notes": None
    }
