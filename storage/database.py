"""
storage/database.py — SQLite database initialization and migrations.

Schema follows Section 13 of the ContextClip spec exactly.
All tables are append-only; updates are modeled as annotations.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional


_local = threading.local()


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return a thread-local connection to the SQLite database."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


SCHEMA_SQL = """
-- -----------------------------------------------------------------------
-- Events (immutable; corrections modeled as derived events)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    seq             INTEGER UNIQUE NOT NULL,
    workflow_id     TEXT,
    type            TEXT NOT NULL CHECK(type IN ('copy','paste')),
    timestamp_utc   TEXT NOT NULL,
    source_app_json TEXT NOT NULL,
    dest_app_json   TEXT,
    payload_hash    TEXT NOT NULL,
    payload_type    TEXT NOT NULL,
    preview_text    TEXT NOT NULL DEFAULT '',
    raw_text        TEXT NOT NULL DEFAULT '',
    byte_size       INTEGER NOT NULL DEFAULT 0,
    screenshot_id   TEXT,
    plugin_context_json TEXT,
    entities_json   TEXT NOT NULL DEFAULT '[]',
    parent_event_id TEXT,
    paste_mode      TEXT,
    content_type    TEXT NOT NULL DEFAULT 'text',
    privacy_class   TEXT NOT NULL DEFAULT 'public',
    confidence      REAL NOT NULL DEFAULT 1.0,
    FOREIGN KEY(screenshot_id) REFERENCES screenshots(id)
);

CREATE INDEX IF NOT EXISTS idx_events_workflow ON events(workflow_id);
CREATE INDEX IF NOT EXISTS idx_events_seq ON events(seq);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_events_hash ON events(payload_hash);

-- -----------------------------------------------------------------------
-- Screenshots (content-addressed; deduplicated by sha256)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS screenshots (
    id              TEXT PRIMARY KEY,
    sha256          TEXT UNIQUE NOT NULL,
    local_path      TEXT NOT NULL,
    width           INTEGER NOT NULL DEFAULT 0,
    height          INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    retention_class TEXT NOT NULL DEFAULT 'standard'
);

-- -----------------------------------------------------------------------
-- Graph edges (ReferenceGraph)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS graph_edges (
    id              TEXT PRIMARY KEY,
    from_event_id   TEXT NOT NULL,
    to_event_id     TEXT NOT NULL,
    relation        TEXT NOT NULL,
    score           REAL NOT NULL DEFAULT 1.0,
    source          TEXT NOT NULL DEFAULT 'direct',
    FOREIGN KEY(from_event_id) REFERENCES events(id),
    FOREIGN KEY(to_event_id) REFERENCES events(id)
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON graph_edges(from_event_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON graph_edges(to_event_id);

-- -----------------------------------------------------------------------
-- Context blocks (derived; 7-event compressed windows)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS context_blocks (
    id              TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    event_start     INTEGER NOT NULL,
    event_end       INTEGER NOT NULL,
    event_ids_json  TEXT NOT NULL DEFAULT '[]',
    title           TEXT NOT NULL DEFAULT '',
    one_line_goal   TEXT NOT NULL DEFAULT '',
    narrative       TEXT NOT NULL DEFAULT '',
    entities_json   TEXT NOT NULL DEFAULT '[]',
    decisions_json  TEXT NOT NULL DEFAULT '[]',
    questions_json  TEXT NOT NULL DEFAULT '[]',
    transitions_json TEXT NOT NULL DEFAULT '[]',
    hashes_json     TEXT NOT NULL DEFAULT '[]',
    toon_payload    TEXT NOT NULL DEFAULT '',
    markdown_payload TEXT NOT NULL DEFAULT '',
    model_info_json TEXT NOT NULL DEFAULT '{}',
    safety_json     TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_blocks_workflow ON context_blocks(workflow_id);

-- -----------------------------------------------------------------------
-- Plugins registry
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plugins (
    id              TEXT PRIMARY KEY,
    version         TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'enabled',
    permissions_json TEXT NOT NULL DEFAULT '[]',
    config_json     TEXT NOT NULL DEFAULT '{}',
    last_health     TEXT
);

-- -----------------------------------------------------------------------
-- Hotkeys
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotkeys (
    id              TEXT PRIMARY KEY,
    command_id      TEXT NOT NULL UNIQUE,
    accelerator     TEXT NOT NULL,
    enabled         INTEGER NOT NULL DEFAULT 1
);

-- -----------------------------------------------------------------------
-- Privacy exclusions
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS excluded_apps (
    id              TEXT PRIMARY KEY,
    pattern         TEXT NOT NULL,
    pattern_type    TEXT NOT NULL DEFAULT 'process_name',
    created_at      TEXT NOT NULL
);

-- -----------------------------------------------------------------------
-- FTS5 full-text search over event previews
-- -----------------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    id,
    preview_text,
    content='events',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS events_fts_insert AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, id, preview_text)
    VALUES (new.rowid, new.id, new.preview_text);
END;
"""

DEFAULT_HOTKEYS = [
    ("hk_dashboard", "win+shift+c", "open_dashboard"),
    ("hk_copy_context", "win+shift+x", "copy_context_markdown"),
    ("hk_pause", "win+shift+p", "pause_capture"),
    ("hk_bubble", "win+shift+b", "show_bubble"),
]


def initialize(db_path: Path) -> None:
    """Create the database schema and seed defaults. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)

    # Seed default hotkeys
    for hk_id, accelerator, command_id in DEFAULT_HOTKEYS:
        conn.execute(
            "INSERT OR IGNORE INTO hotkeys(id, command_id, accelerator) VALUES (?,?,?)",
            (hk_id, command_id, accelerator),
        )

    conn.commit()
    print(f"[Storage] Database initialized at {db_path}")
