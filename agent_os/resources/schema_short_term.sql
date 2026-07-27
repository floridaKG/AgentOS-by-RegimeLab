-- Short-term memory SQLite schema for Agent OS.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS st_records (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  message_id TEXT,
  agent_id TEXT NOT NULL,
  workspace TEXT NOT NULL,
  intent TEXT NOT NULL,
  kind TEXT NOT NULL,
  content TEXT NOT NULL,
  summary TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  status TEXT NOT NULL,
  promote_state TEXT NOT NULL DEFAULT 'none',
  fingerprint TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  promoted_at TEXT,
  boundary_kind TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS st_records_fts
USING fts5(id UNINDEXED, content, summary, tokenize = 'porter');

CREATE TABLE IF NOT EXISTS st_tags (
  record_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY (record_id, tag),
  FOREIGN KEY (record_id) REFERENCES st_records(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS st_help_requests (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  parent_agent TEXT NOT NULL,
  requesting_agent TEXT NOT NULL,
  workspace TEXT NOT NULL,
  uncertainty_type TEXT NOT NULL,
  question TEXT NOT NULL,
  recommended_default TEXT NOT NULL,
  status TEXT NOT NULL,
  resolution_record_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS st_packet_context (
  packet_run_id TEXT PRIMARY KEY,
  workspace TEXT NOT NULL,
  intent TEXT NOT NULL,
  query TEXT NOT NULL,
  context_json TEXT NOT NULL,
  token_budget INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS st_decisions (
  fingerprint TEXT PRIMARY KEY,
  decision TEXT NOT NULL,
  note TEXT,
  decided_at TEXT NOT NULL,
  decided_by TEXT,
  spec_path TEXT
);
