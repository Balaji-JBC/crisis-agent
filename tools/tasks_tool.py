"""Google Tasks tool — ADK function tool wrapper."""

from googleapiclient.discovery import build
import google.auth
import os


def _service():
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/tasks"]
    )
    return build("tasks", "v1", credentials=creds, cache_discovery=False)


def create_task(title: str, notes: str = "") -> dict:
    """
    Add a task to Google Tasks.

    Args:
        title: Task title (e.g. "Buy 2L water bottles").
        notes: Optional detail or instructions.

    Returns:
        dict with task_id and title.
    """
    list_id = os.getenv("GOOGLE_TASKLIST_ID", "@default")
    body    = {"title": title, "notes": notes}
    task    = _service().tasks().insert(tasklist=list_id, body=body).execute()
    return {"task_id": task["id"], "title": task["title"]}