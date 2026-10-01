-- Local SQLite schema, version 1. Kept deliberately small.
CREATE TABLE IF NOT EXISTS glossaries (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS terminology (
    id               INTEGER PRIMARY KEY,
    glossary_id      INTEGER NOT NULL REFERENCES glossaries(id) ON DELETE CASCADE,
    source_term      TEXT NOT NULL,
    target_term      TEXT NOT NULL,
    source_lang      TEXT NOT NULL,
    target_lang      TEXT NOT NULL,
    category         TEXT NOT NULL DEFAULT '',
    context          TEXT NOT NULL DEFAULT '',     -- keyword(s): entry applies only when they occur nearby
    notes            TEXT NOT NULL DEFAULT '',
    do_not_translate INTEGER NOT NULL DEFAULT 0,
    priority         TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (glossary_id, source_term, source_lang, target_lang, context)
);

-- Contains document text. Disabled with use_memory = false; emptied with `sbt history clear`.
CREATE TABLE IF NOT EXISTS translation_memory (
    id           INTEGER PRIMARY KEY,
    source_lang  TEXT NOT NULL,
    target_lang  TEXT NOT NULL,
    source_text  TEXT NOT NULL,                    -- with formatting tags, as sent to the engine
    target_text  TEXT NOT NULL,
    origin       TEXT NOT NULL CHECK (origin IN ('model', 'human')),   -- human edits win
    model        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_lang, target_lang, source_text, origin)
);
CREATE INDEX IF NOT EXISTS ix_tm_pair ON translation_memory(source_lang, target_lang);

-- No document text here: names, counts and timings only.
CREATE TABLE IF NOT EXISTS translation_jobs (
    id            INTEGER PRIMARY KEY,
    file_name     TEXT NOT NULL,
    file_type     TEXT NOT NULL,
    source_lang   TEXT NOT NULL,
    target_lang   TEXT NOT NULL,
    model         TEXT NOT NULL,
    mode          TEXT NOT NULL CHECK (mode IN ('offline', 'online')),
    segments      INTEGER NOT NULL,
    translated    INTEGER NOT NULL,
    warnings      INTEGER NOT NULL,
    seconds       REAL NOT NULL,
    finished_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
