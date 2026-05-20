PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS brand (
  id                TEXT PRIMARY KEY,
  display           TEXT NOT NULL,
  config_json       TEXT NOT NULL,
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS category (
  id                TEXT PRIMARY KEY,
  display           TEXT NOT NULL,
  aliases_json      TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS product (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  brand_id          TEXT NOT NULL REFERENCES brand(id),
  category_id       TEXT NOT NULL REFERENCES category(id),
  model_name        TEXT NOT NULL,
  model_code        TEXT,
  first_seen_at     TEXT NOT NULL DEFAULT (datetime('now')),
  last_refreshed_at TEXT,
  is_active         INTEGER NOT NULL DEFAULT 1,
  UNIQUE(brand_id, model_code)
);
CREATE INDEX IF NOT EXISTS idx_product_brand_category ON product(brand_id, category_id);
CREATE INDEX IF NOT EXISTS idx_product_model_name      ON product(model_name);

CREATE TABLE IF NOT EXISTS product_source_ref (
  product_id        INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  source_id         TEXT NOT NULL,
  external_id       TEXT NOT NULL,
  url               TEXT NOT NULL,
  last_fetched_at   TEXT,
  PRIMARY KEY (product_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_psr_source_external ON product_source_ref(source_id, external_id);

CREATE TABLE IF NOT EXISTS spec_raw (
  product_id        INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  source_id         TEXT NOT NULL,
  payload_json      TEXT NOT NULL,
  captured_at       TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (product_id, source_id, captured_at)
);

CREATE TABLE IF NOT EXISTS spec_fact (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id        INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  canonical_key     TEXT NOT NULL,
  value_num         REAL,
  value_text        TEXT,
  unit              TEXT NOT NULL,
  source_id         TEXT NOT NULL,
  source_attr_label TEXT,
  confidence        REAL NOT NULL,
  matched_by        TEXT NOT NULL,
  captured_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_spec_fact_product_key ON spec_fact(product_id, canonical_key);
CREATE INDEX IF NOT EXISTS idx_spec_fact_key         ON spec_fact(canonical_key);

CREATE TABLE IF NOT EXISTS raw_review (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id        INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  source_id         TEXT NOT NULL,
  author_hash       TEXT,
  rating            REAL,
  text              TEXT NOT NULL,
  posted_at         TEXT,
  fetched_at        TEXT NOT NULL DEFAULT (datetime('now')),
  url               TEXT,
  language          TEXT NOT NULL DEFAULT 'ko',
  text_hash         TEXT NOT NULL,
  UNIQUE(product_id, source_id, text_hash)
);
CREATE INDEX IF NOT EXISTS idx_review_product_posted ON raw_review(product_id, posted_at);

CREATE TABLE IF NOT EXISTS review_summary (
  product_id        INTEGER PRIMARY KEY REFERENCES product(id) ON DELETE CASCADE,
  pros_json         TEXT NOT NULL,
  cons_json         TEXT NOT NULL,
  sentiment_tags_json TEXT NOT NULL,
  overall_score     REAL NOT NULL,
  evidence_count    INTEGER NOT NULL,
  caveats_json      TEXT NOT NULL DEFAULT '[]',
  generated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  model_used        TEXT NOT NULL,
  input_hash        TEXT NOT NULL,
  status            TEXT NOT NULL DEFAULT 'ok'
);

CREATE TABLE IF NOT EXISTS product_image (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id        INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
  source_id         TEXT NOT NULL,
  idx               INTEGER NOT NULL,
  original_url      TEXT NOT NULL,
  local_path        TEXT,
  width             INTEGER,
  height            INTEGER,
  bytes             INTEGER,
  is_primary        INTEGER NOT NULL DEFAULT 0,
  fetched_at        TEXT,
  status            TEXT NOT NULL DEFAULT 'ok',
  UNIQUE(product_id, idx)
);
CREATE INDEX IF NOT EXISTS idx_image_primary ON product_image(product_id, is_primary);

CREATE TABLE IF NOT EXISTS refresh_log (
  run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at          TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at         TEXT,
  scope_brands_json     TEXT NOT NULL DEFAULT '[]',
  scope_categories_json TEXT NOT NULL DEFAULT '[]',
  scope_product_ids_json TEXT NOT NULL DEFAULT '[]',
  status              TEXT NOT NULL DEFAULT 'pending',
  items_processed     INTEGER NOT NULL DEFAULT 0,
  error_text          TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_status ON refresh_log(status, started_at);

CREATE TABLE IF NOT EXISTS llm_call_log (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id        INTEGER REFERENCES product(id) ON DELETE SET NULL,
  purpose           TEXT NOT NULL,
  model             TEXT NOT NULL,
  input_tokens      INTEGER NOT NULL,
  output_tokens     INTEGER NOT NULL,
  cost_usd          REAL NOT NULL,
  latency_ms        INTEGER NOT NULL,
  cache_hit         INTEGER NOT NULL DEFAULT 0,
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_llm_created ON llm_call_log(created_at);

INSERT INTO schema_migrations (version) VALUES ('0001_init');
