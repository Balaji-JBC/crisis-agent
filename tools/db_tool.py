"""
Cloud SQL tools — ADK function tool wrappers.
Uses Cloud SQL Python Connector (Public IP, no VPC needed).
"""

import os
from google.cloud.sql.connector import Connector
import pg8000

_connector = Connector()


def _get_conn():
    return _connector.connect(
        os.getenv("CLOUDSQL_INSTANCE_CONNECTION_NAME"),
        "pg8000",
        user="postgres",
        password=os.getenv("CLOUDSQL_PASS", ""),
        db="crisis_planner",
    )


def log_session(
    crisis_input: str,
    severity: str,
    action_plan: str,
    calendar_events_created: int,
    tasks_created: int,
) -> dict:
    """
    Save a completed crisis session to the database.

    Args:
        crisis_input:            Original user crisis description.
        severity:                Severity level (mild/moderate/severe).
        action_plan:             Full action plan as a JSON string.
        calendar_events_created: Number of calendar events created.
        tasks_created:           Number of tasks created.

    Returns:
        dict with session_id.
    """
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO crisis_sessions
           (crisis_input, severity, action_plan,
            calendar_events_created, tasks_created)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (crisis_input, severity, action_plan,
         calendar_events_created, tasks_created),
    )
    session_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return {"session_id": str(session_id), "status": "saved"}


def get_past_sessions(crisis_type: str, limit: int = 3) -> dict:
    """
    Recall similar past crisis sessions from the database.

    Args:
        crisis_type: Keyword describing the crisis (e.g. "lockdown").
        limit:       Max number of past sessions to return.

    Returns:
        dict with list of past sessions.
    """
    conn   = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT crisis_input, severity, action_plan, created_at
           FROM crisis_sessions
           WHERE crisis_input ILIKE %s
           ORDER BY created_at DESC LIMIT %s""",
        (f"%{crisis_type}%", limit),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {
        "past_sessions": [
            {"crisis_input": r[0], "severity": r[1],
             "action_plan": r[2], "created_at": str(r[3])}
            for r in rows
        ]
    }