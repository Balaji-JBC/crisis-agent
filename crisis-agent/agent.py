import os
import logging
import google.cloud.logging
from dotenv import load_dotenv
from datetime import datetime
from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools import google_search

# Assuming these are your custom tools
from .tools.calendar_tool import create_calendar_event
from .tools.tasks_tool    import create_task
from .tools.db_tool       import log_session, get_past_sessions
from .tools.execute_tool  import execute_action_plan

# Setup
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
    """Saves the user's crisis details to shared agent state."""
    tool_context.state["CRISIS_INPUT"] = crisis_input
    tool_context.state["SEVERITY"]     = severity
    tool_context.state["LOCATION"]     = location
    return {"status": "session_started"}


def get_researcher_instruction():
    today = datetime.now().strftime("%Y-%m-%d")
    return f"""
Search Google for current, real-world information regarding the following situation: 
{{ CRISIS_INPUT }} in {{ LOCATION }} (severity: {{ SEVERITY }}).

Today's date is {today}. All calendar_events must use dates from {today} onwards. Never use past dates.

Based on your search, create a structured action plan. If the crisis spans multiple days, ensure your calendar events reflect that duration. Include specific, actionable steps to perform inside the event 'description'.

Return ONLY valid JSON, no markdown formatting, no extra text:
{{
  "summary": "One sentence summary of the situation based on your search.",
  "severity": "mild|moderate|severe",
  "calendar_events": [
    {{
      "title": "...", 
      "start_iso": "{today}T09:00:00+05:30", 
      "end_iso": "{today}T18:00:00+05:30", 
      "description": "List of actions: 1. Stay indoors. 2. Drink water..."
    }}
  ],
  "tasks": [{{"title": "...", "notes": "..."}}],
  "warnings": ["...", "...", "..."]
}}
"""

researcher_planner_agent = Agent(
    name="researcher_planner",
    model=MODEL,
    description="Researches the crisis using Google Search and returns a structured action plan as JSON.",
    instruction=get_researcher_instruction(),
    tools=[google_search],
    output_key="action_plan",
)


executor_presenter_agent = Agent(
    name="executor_presenter",
    model=MODEL,
    description="Executes the action plan and presents a friendly summary.",
    instruction="""
You have received the planned JSON. Call execute_action_plan with the action_plan string and crisis description.

action_plan:     { action_plan }
crisis_input:    { CRISIS_INPUT }

After the tool returns successfully, write a friendly plain-English summary using the result:
- 🚨 One-sentence situation summary
- 📅 Calendar events scheduled (Confirm the action list was added to the description)
- 📝 Tasks added
- ⚠️ Top 3 warnings
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
If the user provides a scenario (e.g., "severe heat for next 3 days in Bangalore"), extract or ask for:
1. The crisis or emergency situation
2. Severity (mild / moderate / severe)
3. Their city

Once you have all three, call `start_crisis_session` with their answers.
Then call `get_past_sessions` to check for similar past events and note any relevant context.
Finally, hand off to `crisis_workflow`.
""",
    tools=[start_crisis_session, get_past_sessions],
    sub_agents=[crisis_workflow],
)