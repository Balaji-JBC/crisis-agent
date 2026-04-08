import os
import logging
import google.cloud.logging
from dotenv import load_dotenv
from datetime import datetime
from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import google_search

from .tools.calendar_tool import create_calendar_event
from .tools.tasks_tool    import create_task
from .tools.db_tool       import log_session, get_past_sessions
from .tools.execute_tool import execute_action_plan

cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()
load_dotenv()

MODEL = os.getenv("MODEL", "gemini-2.5-flash")


def start_crisis_session(
    tool_context: ToolContext,
    crisis_input: str,
    severity: str,
    location: str,
) -> dict:
    """Saves the user\'s crisis details to shared agent state."""
    tool_context.state["CRISIS_INPUT"] = crisis_input
    tool_context.state["SEVERITY"]     = severity
    tool_context.state["LOCATION"]     = location
    return {"status": "session_started"}


def get_researcher_instruction():
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""
Research this crisis on Wikipedia: {{ CRISIS_INPUT }} in {{ LOCATION }} (severity: {{ SEVERITY }}).
Optionally call get_past_sessions for similar past events.

Today's date is {today}. All calendar_events must use dates from {today} onwards. Never use past dates.

Return ONLY valid JSON, no markdown, no extra text:
{{
  "summary": "one sentence",
  "severity": "mild|moderate|severe",
  "calendar_events": [
    {{"title": "...", "start_iso": "{today}T09:00:00+05:30", "end_iso": "{today}T09:30:00+05:30", "description": "..."}}
  ],
  "tasks": [{{"title": "...", "notes": "..."}}],
  "warnings": ["...", "...", "..."]
}}
"""

researcher_planner_agent = Agent(
    name="researcher_planner",
    model=MODEL,
    description="Researches the crisis on Wikipedia and returns a structured action plan as JSON.",
    instruction=get_researcher_instruction(),
    tools=[google_search],
    output_key="action_plan",
)


executor_presenter_agent = Agent(
    name="executor_presenter",
    model=MODEL,
    description="Executes the action plan and presents a friendly summary.",
    instruction="""
Call execute_action_plan with the action_plan string and crisis description.

action_plan:     { action_plan }
crisis_input:    { CRISIS_INPUT }

After the tool returns, write a friendly plain-English summary using the result:
- One-sentence situation summary
- Calendar events added (✅ from event_titles)
- Tasks added (📝 from task_titles)
- Top 3 warnings (⚠️ from warnings)
""",
    tools=[execute_action_plan],
)


crisis_workflow = SequentialAgent(
    name="crisis_workflow",
    description="Research and plan, then execute and present.",
    sub_agents=[researcher_planner_agent, executor_presenter_agent],
)


def start_crisis_session(
    tool_context: ToolContext,
    crisis_input: str,
    severity: str,
    location: str,
) -> dict:
    """Saves the user's crisis details to shared agent state."""
    tool_context.state["CRISIS_INPUT"] = crisis_input
    tool_context.state["SEVERITY"]     = severity
    tool_context.state["LOCATION"]     = location
    return {"status": "session_started"}


root_agent = Agent(
    name="crisis_planner_orchestrator",
    model=MODEL,
    description="Collects crisis details from the user and runs the crisis planning pipeline.",
    instruction="""
You are the Crisis Planner assistant. Greet the user and ask for:
1. The crisis or emergency situation
2. Severity (mild / moderate / severe)
3. Their city

Once you have all three, call start_crisis_session with their answers.
Then call get_past_sessions to check for similar past events and note any relevant context.
Then hand off to crisis_workflow.
""",
    tools=[start_crisis_session, get_past_sessions],
    sub_agents=[crisis_workflow],
)