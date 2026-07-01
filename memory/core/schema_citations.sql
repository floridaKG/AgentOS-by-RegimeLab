CREATE TABLE IF NOT EXISTS citations (
    ref_id TEXT PRIMARY KEY,
    source_backend TEXT NOT NULL,
    source_namespace TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    snippet TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_citations_created ON citations(created_at);
