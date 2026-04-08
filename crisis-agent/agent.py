import os
import logging
import google.cloud.logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import google_search

from .tools.db_tool      import log_session, get_past_sessions
from .tools.execute_tool import execute_action_plan

try:
    google.cloud.logging.Client().setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)

load_dotenv()

MODEL = os.getenv("MODEL", "gemini-2.5-flash")


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


def get_researcher_instruction():
    today    = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    return f"""
Search Google for current information about: {{ CRISIS_INPUT }} in {{ LOCATION }} (severity: {{ SEVERITY }}).

Today is {today}. Every date in calendar_events must be {today} or later — never in the past.

Create one calendar_event per day of the crisis. Do NOT create a single multi-day event.
For example, a 3-day crisis starting today produces 3 separate events on consecutive days.
Each event runs 09:00–18:00 IST. Include specific actions in each event's description.

Respond with ONLY raw JSON — no markdown, no code fences, no explanation.
The JSON goes directly to the next agent; the user does not see it.

{{
  "summary": "one sentence about the situation",
  "severity": "mild|moderate|severe",
  "calendar_events": [
    {{"title": "Day 1 - ...", "start_iso": "{today}T09:00:00+05:30",    "end_iso": "{today}T18:00:00+05:30",    "description": "1. Action one. 2. Action two."}},
    {{"title": "Day 2 - ...", "start_iso": "{tomorrow}T09:00:00+05:30", "end_iso": "{tomorrow}T18:00:00+05:30", "description": "1. Action one. 2. Action two."}}
  ],
  "tasks":    [{{"title": "...", "notes": "..."}}],
  "warnings": ["...", "...", "..."]
}}
"""


researcher_planner_agent = Agent(
    name="researcher_planner",
    model=MODEL,
    description="Searches Google for crisis info and returns a raw JSON action plan.",
    instruction=get_researcher_instruction(),
    tools=[google_search],
    output_key="action_plan",
)


executor_presenter_agent = Agent(
    name="executor_presenter",
    model=MODEL,
    description="Executes the action plan via tools and returns a friendly summary.",
    instruction="""
Call execute_action_plan with these two arguments:
  action_plan:  { action_plan }
  crisis_input: { CRISIS_INPUT }

Return the tool's response exactly as-is. Do not add, remove, or rephrase anything.
""",
    tools=[execute_action_plan],
)


crisis_workflow = SequentialAgent(
    name="crisis_workflow",
    description="Research and plan, then execute and present.",
    sub_agents=[researcher_planner_agent, executor_presenter_agent],
)


root_agent = Agent(
    name="crisis_planner_orchestrator",
    model=MODEL,
    description="Collects crisis details from the user and runs the crisis planning pipeline.",
    instruction="""
You are the Crisis Planner assistant.
If the user provides a scenario (e.g. "severe heat for 3 days in Bangalore"), extract the details.
Otherwise ask for:
  1. The crisis or emergency situation
  2. Severity (mild / moderate / severe)
  3. Their city

Once you have all three, call start_crisis_session with their answers.
Then call get_past_sessions to check for similar past events and note relevant context.
Then hand off to crisis_workflow.
""",
    tools=[start_crisis_session, get_past_sessions],
    sub_agents=[crisis_workflow],
)