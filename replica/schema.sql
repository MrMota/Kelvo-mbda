-- MBDAflow schema (SQLite). Single-tenant, self-hosted: one local owner, so no
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
