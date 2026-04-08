"""Google Calendar tool — ADK function tool wrapper."""

from googleapiclient.discovery import build
import google.auth
import os


def _service():
    # Uses ADC (Application Default Credentials)
    # Works automatically in Cloud Shell and Cloud Run
    # No service_account.json needed
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/calendar"]
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_calendar_event(
    title: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
) -> dict:
    """
    Create a Google Calendar event.

    Args:
        title:       Event title.
        start_iso:   Start datetime ISO 8601, e.g. "2026-04-09T09:00:00+05:30".
        end_iso:     End datetime ISO 8601.
        description: Optional event description.

    Returns:
        dict with event_id and link.
    """
    cal_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    event  = {
        "summary":     title,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": "Asia/Kolkata"},
        "end":   {"dateTime": end_iso,   "timeZone": "Asia/Kolkata"},
    }
    created = _service().events().insert(calendarId=cal_id, body=event).execute()
    return {"event_id": created["id"], "link": created.get("htmlLink", "")}