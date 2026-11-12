-- Kelvo schema (SQLite). Single-tenant, self-hosted: one local owner, so no
-- user_id columns yet. Access rule: the UI is local; the run/MCP APIs require an
-- API key checked once per request in the API layer (app/auth.py).
-- ids are uuid4 text; times are ISO-8601 UTC text.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS flows (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  data TEXT NOT NULL DEFAULT '{"nodes":[],"edges":[]}',   -- json graph
  endpoint_name TEXT UNIQUE,                               -- alias for /run
  locked INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0,1)),
  mcp_enabled INTEGER NOT NULL DEFAULT 0 CHECK (mcp_enabled IN (0,1)),
  mcp_tool_name TEXT,
  mcp_description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS flows_project ON flows(project_id, updated_at);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  flow_id TEXT NOT NULL REFERENCES flows(id) ON DELETE CASCADE,
  session_id TEXT NOT NULL,
  sender TEXT NOT NULL CHECK (sender IN ('user','machine')),
  sender_name TEXT NOT NULL,
  text TEXT NOT NULL,
  properties TEXT NOT NULL DEFAULT '{}',                   -- json: steps/tool calls
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_session ON messages(flow_id, session_id, created_at);

CREATE TABLE IF NOT EXISTS variables (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL DEFAULT 'generic' CHECK (type IN ('generic','credential')),
  value TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,                           -- sha256, key shown once
  prefix TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  flow_id TEXT NOT NULL REFERENCES flows(id) ON DELETE CASCADE,
  session_id TEXT,
  status TEXT NOT NULL CHECK (status IN ('running','success','error')),
  error TEXT,
  trace TEXT NOT NULL DEFAULT '[]',                        -- json per-node timings
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS runs_flow ON runs(flow_id, started_at);

CREATE TABLE IF NOT EXISTS skills (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE CHECK (name GLOB '[a-z0-9]*' AND length(name) <= 64),
  description TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vector_chunks (
  id TEXT PRIMARY KEY,
  collection TEXT NOT NULL,
  text TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}',
  embedding TEXT NOT NULL,                                 -- json float array
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS vector_chunks_collection ON vector_chunks(collection);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Single owner account. Kelvo is one person's tool: the API refuses a second user.
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,           -- scrypt$n$r$p$salt$hash
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,           -- sha256 of the cookie value
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);

-- Long-term memory: facts agents remember about you across chats (Settings → Memory).
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Scheduled runs: send a message to a flow daily at a time, or every N minutes.
CREATE TABLE IF NOT EXISTS schedules (
  id TEXT PRIMARY KEY,
  flow_id TEXT NOT NULL REFERENCES flows(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  message TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('daily', 'interval')),
  time_of_day TEXT,                 -- daily: HH:MM (this computer's local time)
  days TEXT NOT NULL DEFAULT '0123456', -- daily: weekdays it runs, 0 = Monday
  every_minutes INTEGER,            -- interval
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
  next_run TEXT,                    -- ISO local time
  last_run TEXT,
  last_status TEXT,
  last_output TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS schedules_due ON schedules(enabled, next_run);
