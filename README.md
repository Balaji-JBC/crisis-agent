# Crisis Planner 🚨

An AI-powered emergency preparedness assistant built on Google ADK. Describe any crisis in plain English and get a real-time action plan automatically scheduled into Google Calendar and Google Tasks.

***

## What It Does

Type something like *"severe heatwave in Bangalore for 3 days"* and Crisis Planner will:

1. Search the web for real-time crisis information
2. Build a structured day-by-day action plan
3. Create Google Calendar events — one per day of the crisis
4. Create Google Tasks with specific actionable steps
5. Log the session to Cloud SQL for future recall
6. Return a friendly plain-English summary

***

## Architecture

```
User Prompt
    │
Root Agent (Orchestrator)
├── Saves crisis, severity, location → Agent State
├── Checks past sessions → Cloud SQL
└── Hands off to SequentialAgent pipeline
        │
        ▼
Researcher Agent
└── google_search → real-time data → JSON action plan
        │
        ▼
Executor Agent
├── create_calendar_event (1 per day)
├── create_task (per action item)
└── log_session → Cloud SQL
        │
        ▼
Actionable Summary shown to user
```

***

## Tech Stack

| Service | Purpose |
|---|---|
| Google ADK | Multi-agent orchestration (SequentialAgent, Agent) |
| Gemini 2.5 Flash | LLM for all agents via Google AI |
| Google Search (grounding) | Real-time crisis research |
| Google Calendar API | Scheduling daily action events |
| Google Tasks API | Creating preparedness checklists |
| Cloud Run | Serverless deployment |
| Cloud SQL (PostgreSQL) | Session history storage |
| Cloud Logging | Production observability |
| Service Account + IAM | Secure Google API authentication |

***

## Project Structure

```
crisis-agent/
├── crisis_agent/
│   ├── __init__.py
│   ├── agent.py              # All agents defined here
│   └── tools/
│       ├── calendar_tool.py  # create_calendar_event
│       ├── tasks_tool.py     # create_task
│       ├── db_tool.py        # log_session, get_past_sessions
│       └── execute_tool.py   # execute_action_plan (handles all tool calls)
├── .env
├── requirements.txt
└── README.md
```

***

## Local Setup

### Prerequisites

- Python 3.11+
- Google Cloud project with billing enabled
- Google Calendar API and Tasks API enabled
- A service account with Calendar writer access
- A Gemini API key from [aistudio.google.com](https://aistudio.google.com)

### Steps

```bash
# Clone the repo
git clone <your-repo-url>
cd crisis-agent

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your values

# Run locally
adk run crisis_agent
```

***

## Environment Variables

```env
GOOGLE_API_KEY=your_gemini_api_key
MODEL=gemini-2.5-flash
GOOGLE_CALENDAR_ID=your_calendar_id@group.calendar.google.com
CLOUDSQL_INSTANCE_CONNECTION_NAME=project:region:instance
CLOUDSQL_PASS=your_db_password
```

> **Note:** `GOOGLE_CALENDAR_ID` should be the calendar owned by the service account.
> Run the Calendar setup script once to create it and share it to your Gmail.

***

## Deploy to Cloud Run

```bash
uvx --from google-adk==1.0.0 \
adk deploy cloud_run \
  --project=$PROJECT_ID \
  --region=$GOOGLE_CLOUD_LOCATION \
  --service_name=crisis-agent \
  --with_ui \
  . \
  -- \
  --service-account=$SERVICE_ACCOUNT \
  --timeout=3600 \
  --min-instances=1
```

After deploying, update environment variables directly without a full redeploy:

```bash
gcloud run services update crisis-agent \
  --region=us-central1 \
  --update-env-vars GOOGLE_CALENDAR_ID=your_calendar_id
```

***

## Usage

Open the deployed URL and describe your crisis:

> *"There's a severe flood warning in Chennai for the next 3 days"*

The agent will ask for severity and location if not provided, then run the full pipeline automatically.

***

## Key Design Decisions

**Single `execute_action_plan` tool**
Instead of having the LLM call Calendar and Tasks APIs individually (which caused malformed function calls), all execution is handled in one Python function. This is more reliable and reduces the chance of the model generating code instead of tool calls.

**`google_search` isolated in researcher**
Google's API requires that when a grounding tool is present, all tools in the same agent must also be search tools. `researcher_planner` uses only `google_search` to avoid this conflict.

**Date injected at startup**
Today's date is baked into the researcher instruction at server startup so calendar events are always scheduled from the current date forward — never in the past.

**3 LLM calls total**
Root agent → researcher/planner → executor/presenter. Merged from an original 5-agent design for lower latency and fewer timeout risks on Cloud Run.

**Service account has editor access on the calendar**
The service account has editor access on a shared Google Calendar owned by the user's Gmail account.

***

## License

MIT
