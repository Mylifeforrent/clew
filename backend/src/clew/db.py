"""SQLite connection and table DDL. The schema follows the Clew data model document.

Implementation additions versus the documented M1/M3 (all backward compatible):
- import_batch gains rolled_back_at / rolled_back_by: rollback audit trail
  (business rule #6), while keeping change_log as read-only history so that
  replay/re-import stays idempotent.
- M3 adds rollback_record: audit for version-tag rollbacks (rollbacks do not
  write change_log, to avoid a subsequent rollback reversing the rollback log),
  data model §2.10 / §7.
- Time columns uniformly store ISO8601 UTC text (SQLite TEXT affinity).
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from .config import db_path

DDL = """
CREATE TABLE IF NOT EXISTS user (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  role TEXT NOT NULL CHECK(role IN ('admin','editor','viewer')),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_file (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  original_name TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  sha256 TEXT NOT NULL UNIQUE,
  size_bytes INTEGER,
  src_type TEXT NOT NULL CHECK(src_type IN ('csv','xlsx','json')),
  uploaded_by TEXT NOT NULL REFERENCES user(username),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset (
  id TEXT PRIMARY KEY,
  name TEXT,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS field (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL REFERENCES dataset(id),
  name TEXT NOT NULL,
  field_type TEXT,
  source_file_id INTEGER NOT NULL REFERENCES source_file(id),
  src_locator TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(dataset_id, name)
);

CREATE TABLE IF NOT EXISTS edge (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_dataset TEXT NOT NULL,
  from_field TEXT,
  to_dataset TEXT NOT NULL,
  to_field TEXT,
  transform TEXT,
  confidence REAL DEFAULT 1.0 CHECK(confidence >= 0 AND confidence <= 1),
  source TEXT NOT NULL CHECK(source IN ('imported','manual','ai')),
  note TEXT,
  created_by TEXT,
  updated_by TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(from_dataset, from_field, to_dataset, to_field),
  FOREIGN KEY (from_dataset, from_field) REFERENCES field(dataset_id, name),
  FOREIGN KEY (to_dataset, to_field) REFERENCES field(dataset_id, name)
);

CREATE TABLE IF NOT EXISTS import_batch (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  version_no INTEGER NOT NULL UNIQUE,
  file_names TEXT,
  format TEXT NOT NULL CHECK(format IN ('csv','xlsx','json')),
  report TEXT,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  rolled_back_at TEXT,
  rolled_back_by TEXT
);

CREATE TABLE IF NOT EXISTS version_tag (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  note TEXT,
  batch_id INTEGER REFERENCES import_batch(id),
  change_seq INTEGER NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_kind TEXT NOT NULL CHECK(target_kind IN ('dataset','field','edge')),
  target_id TEXT NOT NULL,
  body TEXT NOT NULL,
  author TEXT NOT NULL REFERENCES user(username),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS change_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER REFERENCES import_batch(id),
  entity_kind TEXT NOT NULL CHECK(entity_kind IN ('dataset','field','edge')),
  entity_key TEXT NOT NULL,
  op TEXT NOT NULL CHECK(op IN ('added','updated','deleted')),
  before TEXT,
  after TEXT,
  actor TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- M3: audit records for rollbacks to a version tag. The rollback itself does not
-- write change_log (otherwise the next rollback would reverse the rollback log,
-- breaking idempotence); the operator/time/reverted range are recorded here,
-- satisfying "every write leaves a trail".
CREATE TABLE IF NOT EXISTS rollback_record (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tag_name TEXT NOT NULL REFERENCES version_tag(name),
  from_change_seq INTEGER NOT NULL,
  to_change_seq INTEGER NOT NULL,
  reverted INTEGER NOT NULL,
  actor TEXT NOT NULL REFERENCES user(username),
  created_at TEXT NOT NULL
);

-- M5: AI description draft workspace (data model §2.11). Drafts never touch
-- field.description; once the user accepts, an annotation is written; rejected
-- fields are not generated again.
CREATE TABLE IF NOT EXISTS description_draft (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  dataset_id TEXT NOT NULL REFERENCES dataset(id),
  field_name TEXT NOT NULL,
  draft TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','accepted','rejected')),
  created_at TEXT NOT NULL,
  decided_at TEXT,
  FOREIGN KEY (dataset_id, field_name)
    REFERENCES field(dataset_id, name) ON DELETE CASCADE ON UPDATE CASCADE,
  UNIQUE (dataset_id, field_name, status)
);

CREATE INDEX IF NOT EXISTS idx_edge_to ON edge(to_dataset, to_field);
CREATE INDEX IF NOT EXISTS idx_edge_from ON edge(from_dataset, from_field);
CREATE INDEX IF NOT EXISTS idx_field_sf ON field(source_file_id);
CREATE INDEX IF NOT EXISTS idx_log_entity ON change_log(entity_kind, entity_key);
CREATE INDEX IF NOT EXISTS idx_log_batch ON change_log(batch_id);
CREATE INDEX IF NOT EXISTS idx_annot_target ON annotation(target_kind, target_id);
CREATE INDEX IF NOT EXISTS idx_rollback_tag ON rollback_record(tag_name, id);

-- Partial unique indexes: SQLite treats UNIQUE over combinations containing NULL
-- with NULLS DISTINCT semantics, so table-level edges (both from_field/to_field
-- NULL) escape the UNIQUE constraint above; cover the field-level / table-level
-- forms separately (data model §2.5).
CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_field ON edge(from_dataset, from_field, to_dataset, to_field) WHERE from_field IS NOT NULL AND to_field IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_edge_table ON edge(from_dataset, to_dataset) WHERE from_field IS NULL AND to_field IS NULL;
"""


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()
