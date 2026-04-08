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


# ── Logging + env ─────────────────────────────────────────────────
cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()
load_dotenv()

MODEL = os.getenv("MODEL", "gemini-2.5-flash")


# ── Wikipedia tool ────────────────────────────────────────────────
wikipedia_tool = LangchainTool(
    tool=WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())
)


# ── State tool: saves crisis input ────────────────────────────────
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
    logging.info(f"[State] Crisis session started: {crisis_input}")
    return {"status": "session_started"}


# ─────────────────────────────────────────────────────────────────
# Sub-Agent 1 — Researcher + Planner  (merged: saves 1 LLM call)
# Reads:  CRISIS_INPUT, SEVERITY, LOCATION from state
# Writes: state["action_plan"] via output_key
# ─────────────────────────────────────────────────────────────────
researcher_planner_agent = Agent(
    name="researcher_planner",
    model=MODEL,
    description="Searches Wikipedia for crisis context then builds a structured action plan.",
    instruction="""
You are the Research and Planning agent in a Crisis Planner system.

You have been given the following details:
Crisis:   { CRISIS_INPUT }
Severity: { SEVERITY }
Location: { LOCATION }

Search Wikipedia to learn about this type of crisis. Look for what it typically involves,
standard safety protocols, essential supplies people need, and key timings or phases.

You may also call get_past_sessions to check if similar crises have been handled before.

After researching, produce a plan. Return ONLY a valid JSON object in this exact format
with no extra text, no markdown, and no code fences:

{
  "summary":  "one sentence describing the situation",
  "severity": "mild | moderate | severe",
  "calendar_events": [
    {
      "title":       "event title",
      "start_iso":   "2026-04-09T09:00:00+05:30",
      "end_iso":     "2026-04-09T09:30:00+05:30",
      "description": "what to do at this time"
    }
  ],
  "tasks": [
    { "title": "task title", "notes": "details about this task" }
  ],
  "warnings": ["warning 1", "warning 2", "warning 3"]
}

Use today's date as the reference for scheduling. Return ONLY valid JSON.
""",
    tools=[wikipedia_tool, get_past_sessions],
    output_key="action_plan",
)


# ─────────────────────────────────────────────────────────────────
# Sub-Agent 2 — Executor + Presenter  (merged: saves 1 LLM call)
# Reads:  action_plan, CRISIS_INPUT from state
# Creates Calendar events, Tasks, logs session, then presents
# ─────────────────────────────────────────────────────────────────
executor_presenter_agent = Agent(
    name="executor_presenter",
    model=MODEL,
    description="Creates Google Calendar events and Tasks, logs the session, then presents results.",
    instruction="""
You are the Executor and Presenter agent in a Crisis Planner system.

You have an action plan to carry out. Do not write any code. Do not use print statements.
Just call the tools and then write your summary.

Here is the action plan:
{ action_plan }

Crisis description: { CRISIS_INPUT }

Start by using the create_calendar_event tool for every event listed in calendar_events.
Call it once per event with the title, start_iso, end_iso, and description from the plan.

Next, use the create_task tool for every item listed in tasks.
Call it once per task with the title and notes from the plan.

Then use the log_session tool exactly once to record this session.
Pass the crisis description, the severity from the plan, the full action plan as a string,
the number of calendar events you created, and the number of tasks you created.

After all the tools have finished, write a friendly and reassuring plain-English summary
for the user. Your summary should include:
- A one-sentence description of the situation
- The calendar events that were added, listed by title with a checkmark
- The tasks that were added, listed by title with a notepad emoji
- The top three warnings from the plan

Do not include any raw JSON or code blocks in your final response.
""",
    tools=[create_calendar_event, create_task, log_session],
)


# ── Sequential pipeline ───────────────────────────────────────────
crisis_workflow = SequentialAgent(
    name="crisis_workflow",
    description="Runs the full pipeline: research and plan, then execute and present.",
    sub_agents=[
        researcher_planner_agent,
        executor_presenter_agent,
    ],
)


# ── Root Agent  ← ADK entry point ────────────────────────────────
root_agent = Agent(
    name="crisis_planner_orchestrator",
    model=MODEL,
    description="Crisis Planner entry point. Collects crisis details then runs the full pipeline.",
    instruction="""
You are the Crisis Planner assistant. Greet the user warmly.

Ask them to tell you three things:
- What the crisis or emergency situation is
- How severe it seems to them (mild, moderate, or severe)
- What city or location they are in

Once they have provided all three, call the start_crisis_session tool with their answers.
Then immediately hand off to the crisis_workflow to handle the rest.
""",
    tools=[start_crisis_session],
    sub_agents=[crisis_workflow],
)
