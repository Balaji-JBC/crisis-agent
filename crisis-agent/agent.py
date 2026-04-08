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

# ── Logging + env ─────────────────────────────
cloud_logging_client = google.cloud.logging.Client()
cloud_logging_client.setup_logging()
load_dotenv()

MODEL = os.getenv("MODEL", "gemini-2.5-flash")

# ── Wikipedia Tool (LangchainTool — proven pattern) ───────────────
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

# ─────────────────────────────────────────────
# Sub-Agent 1 — Info Gatherer
# Reads:  CRISIS_INPUT, LOCATION from state
# Writes: state["raw_info"]  via output_key
# ─────────────────────────────────────────────
info_gatherer_agent = Agent(
    name="info_gatherer",
    model=MODEL,
    description="Searches Wikipedia for crisis background, protocols, and supplies needed.",
    instruction="""
You are the Information Gatherer sub-agent in a Crisis Planner system.

Search Wikipedia to research the following crisis:

Crisis:   { CRISIS_INPUT }
Location: { LOCATION }

Find:
  1. What this kind of event typically involves
  2. Standard safety protocols
  3. Essential supplies people need
  4. Key timings or phases

Return ONLY this JSON (no extra text):
{
  "background":  "2-3 sentence summary",
  "protocols":   ["step 1", "step 2"],
  "supplies":    ["item 1", "item 2"],
  "key_timings": ["timing note 1"]
}
""",
    tools=[wikipedia_tool],
    output_key="raw_info",
)

# ─────────────────────────────────────────────
# Sub-Agent 2 — Action Planner
# Reads:  raw_info, CRISIS_INPUT, SEVERITY from state
# Writes: state["action_plan"]  via output_key
# ─────────────────────────────────────────────
action_planner_agent = Agent(
    name="action_planner",
    model=MODEL,
    description="Converts gathered info into a structured action plan.",
    instruction="""
You are the Action Planner sub-agent in a Crisis Planner system.

Crisis:   { CRISIS_INPUT }
Severity: { SEVERITY }

Research findings:
{ raw_info }

Optionally call get_past_sessions to recall similar past crises.

Return ONLY this JSON:
{
  "summary":  "one sentence",
  "severity": "mild | moderate | severe",
  "calendar_events": [
    {
      "title":       "Check government announcement",
      "start_iso":   "2026-04-09T09:00:00+05:30",
      "end_iso":     "2026-04-09T09:30:00+05:30",
      "description": "Monitor official updates"
    }
  ],
  "tasks": [
    { "title": "Buy 5L water", "notes": "Get from nearest supermarket" }
  ],
  "warnings": ["Stay indoors after 6pm"]
}

Use today's date as reference. Return ONLY valid JSON.
""",
    tools=[get_past_sessions],
    output_key="action_plan",
)

# ─────────────────────────────────────────────
# Sub-Agent 3 — Executor
# Reads:  action_plan, CRISIS_INPUT from state
# Creates Calendar events, Tasks, logs to DB
# ─────────────────────────────────────────────
executor_agent = Agent(
    name="executor",
    model=MODEL,
    description="Creates Google Calendar events and Tasks, then saves session to DB.",
    instruction="""
You are the Executor sub-agent in a Crisis Planner system.

Execute this action plan completely:
{ action_plan }

Steps — do ALL of them in order:
  1. Call create_calendar_event for EVERY item in calendar_events
  2. Call create_task for EVERY item in tasks
  3. Call log_session once with:
       - crisis_input             = { CRISIS_INPUT }
       - severity                 = severity from the plan
       - action_plan              = the full plan as a string
       - calendar_events_created  = count of events you created
       - tasks_created            = count of tasks you created

After all tool calls, return a short plain-English summary.
""",
    tools=[create_calendar_event, create_task, log_session],
)

# ── Sub-Agent 4 — Presenter ───────────────────
presenter_agent = Agent(
    name="presenter",
    model=MODEL,
    description="Formats the completed crisis plan into a friendly, readable response.",
    instruction="""
You are the Presenter sub-agent. Your job is to present the completed crisis
plan to the user in a friendly, readable format.

Based on the action plan below, present:
  1. A one-line summary of the situation
  2. ✅ What was added to Google Calendar (list the event titles)
  3. 📝 What was added to Google Tasks (list the task titles)
  4. ⚠️  Top 3 warnings to keep in mind

Be conversational and reassuring. NO raw JSON. NO code blocks.

Action plan:
{ action_plan }
""",
)

# ─────────────────────────────────────────────
# Sequential pipeline
# ─────────────────────────────────────────────
crisis_workflow = SequentialAgent(
    name="crisis_workflow",
    description="Runs the full pipeline: gather info → plan → execute.",
    sub_agents=[
        info_gatherer_agent,
        action_planner_agent,
        executor_agent,
        presenter_agent
    ],
)

# ─────────────────────────────────────────────
# Root Agent  ← ADK entry point
# ─────────────────────────────────────────────
root_agent = Agent(
    name="crisis_planner_orchestrator",
    model=MODEL,
    description="Crisis Planner entry point. Collects crisis details then runs the full pipeline.",
    instruction="""
You are the Crisis Planner assistant.

Greet the user and ask them to describe:
  1. What the crisis or event is
  2. How severe it seems (mild / moderate / severe)
  3. Their location (city)

Once they respond, call start_crisis_session with their answers.
Then immediately transfer control to crisis_workflow.
""",
    tools=[start_crisis_session],
    sub_agents=[crisis_workflow],
)