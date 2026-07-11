-- Organizational AI Memory — full schema (SQLite dialect)
-- Mirrors the Postgres DDL in task.md §3. UUIDs stored as TEXT,
-- JSONB as TEXT (JSON string), BOOLEAN as INTEGER 0/1.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_events (
  id TEXT PRIMARY KEY,
  source_tool TEXT NOT NULL,        -- 'git' | 'claude_chat' | 'n8n'
  title TEXT,
  content TEXT NOT NULL,
  raw_signal TEXT,
  received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  processed INTEGER DEFAULT 0,
  processed_asset_version_id TEXT
);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE,
  team TEXT
);

CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  asset_key TEXT UNIQUE,             -- stable dedup identity (capture pipeline); NULL for seed rows
  type TEXT NOT NULL CHECK (type IN ('prompt', 'workflow', 'agent_config')),
  title TEXT NOT NULL,
  source_tool TEXT NOT NULL,
  owner_id TEXT REFERENCES users(id),
  previous_asset_id TEXT REFERENCES assets(id),
  current_version_id TEXT,
  usage_count INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset_versions (
  id TEXT PRIMARY KEY,
  asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
  raw_event_id TEXT REFERENCES raw_events(id),
  version_number INTEGER NOT NULL,
  content TEXT NOT NULL,
  diff_summary TEXT,
  editor_id TEXT REFERENCES users(id),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(asset_id, version_number)
);

CREATE TABLE IF NOT EXISTS rationale (
  id TEXT PRIMARY KEY,
  version_id TEXT UNIQUE REFERENCES asset_versions(id) ON DELETE CASCADE,
  problem TEXT,
  failed_attempts TEXT,              -- JSON array string
  constraints TEXT,                  -- JSON array string
  confidence TEXT CHECK (confidence IN ('auto', 'user_provided'))
);

CREATE TABLE IF NOT EXISTS rationale_evidence (
  id TEXT PRIMARY KEY,
  rationale_id TEXT REFERENCES rationale(id) ON DELETE CASCADE,
  evidence_type TEXT CHECK (evidence_type IN ('git_diff', 'chat_log', 'user_manual')),
  confidence NUMERIC CHECK (confidence BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS tags (
  id TEXT PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_tags (
  asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
  tag_id TEXT REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (asset_id, tag_id)
);

CREATE TABLE IF NOT EXISTS asset_usage (
  id TEXT PRIMARY KEY,
  asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
  user_id TEXT REFERENCES users(id),
  task_description TEXT,
  used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset_relations (
  id TEXT PRIMARY KEY,
  source_asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
  target_asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
  relation_type TEXT CHECK (relation_type IN ('USES_PROMPT', 'CALLS_AGENT', 'PART_OF_WORKFLOW')),
  CHECK (source_asset_id <> target_asset_id)
);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  source_tool TEXT NOT NULL CHECK (source_tool IN ('chatgpt', 'claude')),
  external_conversation_id TEXT NOT NULL,
  title TEXT,
  owner_id TEXT REFERENCES users(id),
  started_at TIMESTAMP,
  updated_at TIMESTAMP,
  UNIQUE(source_tool, external_conversation_id)
);

CREATE TABLE IF NOT EXISTS conversation_turns (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  external_turn_id TEXT,
  parent_turn_id TEXT REFERENCES conversation_turns(id),
  sequence_number INTEGER NOT NULL,
  speaker_role TEXT NOT NULL CHECK (speaker_role IN ('user', 'assistant', 'system', 'tool')),
  content TEXT NOT NULL,
  model_name TEXT,
  created_at TIMESTAMP,
  content_hash TEXT NOT NULL,
  UNIQUE(conversation_id, sequence_number)
);

CREATE TABLE IF NOT EXISTS turn_feedback (
  id TEXT PRIMARY KEY,
  turn_id TEXT NOT NULL REFERENCES conversation_turns(id) ON DELETE CASCADE,
  feedback_type TEXT NOT NULL CHECK (feedback_type IN ('edit', 'regenerate', 'accept', 'rating')),
  value_json TEXT,
  created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rationale_statements (
  id TEXT PRIMARY KEY,
  version_id TEXT REFERENCES asset_versions(id) ON DELETE CASCADE,
  statement_type TEXT NOT NULL CHECK (statement_type IN ('problem', 'intent', 'constraint', 'failed_attempt', 'outcome')),
  statement TEXT NOT NULL,
  original_statement TEXT NOT NULL,
  evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('observed', 'inferred')),
  confidence NUMERIC NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  alternative_explanation TEXT,
  review_status TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'approved', 'edited', 'rejected')),
  reviewer_id TEXT REFERENCES users(id),
  reviewed_at TIMESTAMP,
  review_note TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rationale_statement_turns (
  statement_id TEXT NOT NULL REFERENCES rationale_statements(id) ON DELETE CASCADE,
  turn_id TEXT NOT NULL REFERENCES conversation_turns(id) ON DELETE CASCADE,
  PRIMARY KEY (statement_id, turn_id)
);

CREATE TABLE IF NOT EXISTS rationale_statement_versions (
  statement_id TEXT NOT NULL REFERENCES rationale_statements(id) ON DELETE CASCADE,
  version_id TEXT NOT NULL REFERENCES asset_versions(id) ON DELETE CASCADE,
  PRIMARY KEY (statement_id, version_id)
);

CREATE TABLE IF NOT EXISTS rationale_statement_commits (
  statement_id TEXT NOT NULL REFERENCES rationale_statements(id) ON DELETE CASCADE,
  raw_event_id TEXT NOT NULL REFERENCES raw_events(id) ON DELETE CASCADE,
  PRIMARY KEY (statement_id, raw_event_id)
);

CREATE TABLE IF NOT EXISTS git_poll_state (
  repo_path TEXT PRIMARY KEY,
  last_polled_sha TEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS intent_reviews (
  id TEXT PRIMARY KEY,
  prompt TEXT NOT NULL,
  source_env TEXT NOT NULL,
  user_name TEXT,
  intent TEXT,
  chat_history TEXT,                 -- JSON array of recent chat messages
  checks TEXT NOT NULL,               -- JSON array of {name, status, detail}
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('passed', 'pending', 'approved', 'rejected')),
  reviewer TEXT,
  resolved_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
