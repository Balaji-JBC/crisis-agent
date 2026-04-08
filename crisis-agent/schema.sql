CREATE TABLE IF NOT EXISTS crisis_sessions (
    id                       SERIAL PRIMARY KEY,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    crisis_input             TEXT NOT NULL,
    severity                 TEXT,
    action_plan              TEXT,
    calendar_events_created  INT DEFAULT 0,
    tasks_created            INT DEFAULT 0
);