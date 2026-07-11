-- Organizational AI Memory — full schema (PostgreSQL dialect)

CREATE TABLE IF NOT EXISTS raw_events (
  id UUID PRIMARY KEY,
  source_tool TEXT NOT NULL,        -- 'git' | 'claude_chat' | 'n8n'
  title TEXT,
  content TEXT NOT NULL,
  raw_signal JSONB,
  received_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  processed BOOLEAN DEFAULT FALSE,
  processed_asset_version_id UUID
);

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE,
  team TEXT
);

CREATE TABLE IF NOT EXISTS assets (
  id UUID PRIMARY KEY,
  asset_key TEXT UNIQUE,             -- stable dedup identity (capture pipeline); NULL for seed rows
  type TEXT NOT NULL CHECK (type IN ('prompt', 'workflow', 'agent_config')),
  title TEXT NOT NULL,
  source_tool TEXT NOT NULL,
  owner_id UUID REFERENCES users(id),
  previous_asset_id UUID REFERENCES assets(id),
  current_version_id UUID,
  usage_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset_versions (
  id UUID PRIMARY KEY,
  asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  raw_event_id UUID REFERENCES raw_events(id),
  version_number INTEGER NOT NULL,
  content TEXT NOT NULL,
  diff_summary TEXT,
  editor_id UUID REFERENCES users(id),
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(asset_id, version_number)
);

CREATE TABLE IF NOT EXISTS rationale (
  id UUID PRIMARY KEY,
  version_id UUID UNIQUE REFERENCES asset_versions(id) ON DELETE CASCADE,
  problem TEXT,
  failed_attempts JSONB,              -- JSON array
  constraints JSONB,                  -- JSON array
  confidence TEXT CHECK (confidence IN ('auto', 'user_provided'))
);

CREATE TABLE IF NOT EXISTS rationale_evidence (
  id UUID PRIMARY KEY,
  rationale_id UUID REFERENCES rationale(id) ON DELETE CASCADE,
  evidence_type TEXT CHECK (evidence_type IN ('git_diff', 'chat_log', 'user_manual')),
  confidence NUMERIC CHECK (confidence BETWEEN 0 AND 1)
);

CREATE TABLE IF NOT EXISTS tags (
  id UUID PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_tags (
  asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (asset_id, tag_id)
);

CREATE TABLE IF NOT EXISTS asset_usage (
  id UUID PRIMARY KEY,
  asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  task_description TEXT,
  used_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset_relations (
  id UUID PRIMARY KEY,
  source_asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  target_asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  relation_type TEXT CHECK (relation_type IN ('USES_PROMPT', 'CALLS_AGENT', 'PART_OF_WORKFLOW')),
  CHECK (source_asset_id <> target_asset_id)
);

CREATE TABLE IF NOT EXISTS git_poll_state (
  repo_path TEXT PRIMARY KEY,
  last_polled_sha TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
