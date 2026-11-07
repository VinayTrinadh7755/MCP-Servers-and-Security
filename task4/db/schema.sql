CREATE TABLE IF NOT EXISTS token_usage (
    request_id TEXT PRIMARY KEY,
    tenant_key TEXT NOT NULL,
    ts_ms INTEGER NOT NULL CHECK (ts_ms >= 0),
    tokens INTEGER NOT NULL CHECK (tokens >= 0),
    status TEXT NOT NULL CHECK (status IN ('reserved', 'reconciled'))
);

CREATE INDEX IF NOT EXISTS idx_token_usage_tenant_ts
    ON token_usage (tenant_key, ts_ms);
