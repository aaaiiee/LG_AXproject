CREATE TABLE IF NOT EXISTS manual_override (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id        INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  canonical_key     TEXT NOT NULL,
  value_num         REAL,
  value_text        TEXT,
  unit              TEXT NOT NULL,
  set_by            TEXT NOT NULL DEFAULT 'user',
  set_at            TEXT NOT NULL DEFAULT (datetime('now')),
  notes             TEXT,
  UNIQUE(product_id, canonical_key)
);
CREATE INDEX IF NOT EXISTS idx_manual_override_product ON manual_override(product_id);

INSERT INTO schema_migrations (version) VALUES ('0002_manual_override');
