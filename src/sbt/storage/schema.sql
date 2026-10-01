-- Local SQLite schema (v1). Kept deliberately small.
CREATE TABLE IF NOT EXISTS glossaries (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    version     INTEGER NOT NULL DEFAULT 1        -- bumped on edit; part of cache key
);

CREATE TABLE IF NOT EXISTS terminology (
    id               INTEGER PRIMARY KEY,
    glossary_id      INTEGER NOT NULL REFERENCES glossaries(id) ON DELETE CASCADE,
    source_term      TEXT NOT NULL,
    target_term      TEXT NOT NULL,
    source_lang      TEXT NOT NULL,
    target_lang      TEXT NOT NULL,
    category         TEXT,
    context          TEXT,                         -- optional: term applies only in this context
    notes            TEXT,
    do_not_translate INTEGER NOT NULL DEFAULT 0,
    priority         TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low','normal','high')),
    UNIQUE (glossary_id, source_term, source_lang, target_lang, context)
);

-- Stores document text: can be disabled and cleared from settings.
CREATE TABLE IF NOT EXISTS translation_memory (
    id           INTEGER PRIMARY KEY,
    source_lang  TEXT NOT NULL,
    target_lang  TEXT NOT NULL,
    source_text  TEXT NOT NULL,
    target_text  TEXT NOT NULL,
    origin       TEXT NOT NULL CHECK (origin IN ('model','human')),  -- human edits win
    cache_key    TEXT,                             -- hash(source, model, prompt ver, glossary ver)
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_tm_cache ON translation_memory(cache_key);

-- No document text here.
CREATE TABLE IF NOT EXISTS translation_jobs (
    id            INTEGER PRIMARY KEY,
    file_name     TEXT NOT NULL,
    file_type     TEXT NOT NULL,
    source_lang   TEXT NOT NULL,
    target_lang   TEXT NOT NULL,
    engine_id     TEXT NOT NULL,
    model         TEXT NOT NULL,
    mode          TEXT NOT NULL CHECK (mode IN ('offline','online')),
    status        TEXT NOT NULL,
    segments      INTEGER,
    translated    INTEGER,
    warnings_json TEXT,
    started_at    TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at   TEXT
);

CREATE TABLE IF NOT EXISTS models (
    id           TEXT PRIMARY KEY,
    file_path    TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    size_bytes   INTEGER NOT NULL,
    installed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
