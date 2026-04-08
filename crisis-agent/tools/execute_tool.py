# tools/execute_tool.py
import json
import logging
from .calendar_tool import create_calendar_event
from .tasks_tool    import create_task
from .db_tool       import log_session

def execute_action_plan(action_plan_json: str, crisis_input: str) -> dict:
    """Parses the action plan and creates all calendar events, tasks, and logs the session."""
    try:
        plan = json.loads(action_plan_json)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    events_created = 0
    tasks_created   = 0
    event_titles    = []
    task_titles     = []

    for event in plan.get("calendar_events", []):
        try:
            create_calendar_event(
                title=event["title"],
                start_iso=event["start_iso"],
                end_iso=event["end_iso"],
                description=event.get("description", "")
            )
            event_titles.append(event["title"])
            events_created += 1
        except Exception as ex:
            logging.warning(f"Calendar event failed: {ex}")

    for task in plan.get("tasks", []):
        try:
            create_task(title=task["title"], notes=task.get("notes", ""))
            task_titles.append(task["title"])
            tasks_created += 1
        except Exception as ex:
            logging.warning(f"Task failed: {ex}")

    log_session(
        crisis_input=crisis_input,
        severity=plan.get("severity", "unknown"),
        action_plan=action_plan_json,
        calendar_events_created=events_created,
        tasks_created=tasks_created
    )

    return {
        "status":         "done",
        "events_created": events_created,
        "tasks_created":  tasks_created,
        "event_titles":   event_titles,
        "task_titles":    task_titles,
        "warnings":       plan.get("warnings", []),
        "summary":        plan.get("summary", "")
    }