import os
import logging
import google.cloud.logging
from dotenv import load_dotenv

from google.adk import Agent
from google.adk.agents import SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.langchain_tool import LangchainTool
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

from .tools.calendar_tool import create_calendar_event
from .tools.tasks_tool    import create_task
from .tools.db_tool       import log_session, get_past_sessions

cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()
load_dotenv()

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

wikipedia_tool = LangchainTool(
    tool=WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())
)


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


researcher_planner_agent = Agent(
    name="researcher_planner",
    model=MODEL,
    description="Researches the crisis on Wikipedia and returns a structured action plan as JSON.",
    instruction="""
Research this crisis on Wikipedia: { CRISIS_INPUT } in { LOCATION } (severity: { SEVERITY }).
Optionally call get_past_sessions for similar past events.

Return ONLY valid JSON, no markdown, no extra text:
{
  "summary": "one sentence",
  "severity": "mild|moderate|severe",
  "calendar_events": [
    {"title": "...", "start_iso": "2026-04-09T09:00:00+05:30", "end_iso": "2026-04-09T09:30:00+05:30", "description": "..."}
  ],
  "tasks": [{"title": "...", "notes": "..."}],
  "warnings": ["...", "...", "..."]
}
""",
    tools=[wikipedia_tool, get_past_sessions],
    output_key="action_plan",
)


executor_presenter_agent = Agent(
    name="executor_presenter",
    model=MODEL,
    description="Executes the action plan using tools, then presents a friendly summary.",
    instruction="""
You have an action plan for: { CRISIS_INPUT }

{ action_plan }

Use your tools in this order:
- Call create_calendar_event once for each event in calendar_events
- Call create_task once for each task in tasks
- Call log_session once with the crisis description, severity, full plan as a string, and counts

Do not write code or use print(). After all tool calls, reply in plain English with:
- One-sentence situation summary
- Calendar events added (✅ title)
- Tasks added (📝 title)
- Top 3 warnings (⚠️)
""",
    tools=[create_calendar_event, create_task, log_session],
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
You are the Crisis Planner assistant. Greet the user and ask for:
1. The crisis or emergency situation
2. Severity (mild / moderate / severe)
3. Their city

Once you have all three, call start_crisis_session, then hand off to crisis_workflow.
""",
    tools=[start_crisis_session],
    sub_agents=[crisis_workflow],
)