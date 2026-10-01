"""Translation memory: reuse earlier translations (exact) and show similar ones to the model (fuzzy).

Contains document text, so it can be switched off (use_memory = false) and emptied (`sbt history clear`).
Every reused translation is re-validated against the *current* glossary before use (see the pipeline).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from sbt.pipeline.tags import strip_tags

FUZZY_THRESHOLD = 80.0      # rapidfuzz ratio (0–100) below which a match is not shown to the model


@dataclass(frozen=True)
class MemoryMatch:
    source: str
    target: str
    origin: str
    score: float


class TranslationMemory:
    def __init__(self, conn: sqlite3.Connection, enabled: bool = True) -> None:
        self.conn = conn
        self.enabled = enabled

    def exact(self, src: str, tgt: str, source_text: str) -> MemoryMatch | None:
        if not self.enabled:
            return None
        row = self.conn.execute(
            "SELECT source_text, target_text, origin FROM translation_memory "
            "WHERE source_lang=? AND target_lang=? AND source_text=? "
            "ORDER BY origin = 'human' DESC, created_at DESC LIMIT 1", (src, tgt, source_text)).fetchone()
        return MemoryMatch(row["source_text"], row["target_text"], row["origin"], 100.0) if row else None

    def similar(self, src: str, tgt: str, text: str, limit: int = 2) -> list[MemoryMatch]:
        """Best fuzzy matches on plain text, excluding the identical sentence."""
        if not self.enabled:
            return []
        plain = strip_tags(text)
        n = len(plain)
        rows = self.conn.execute(
            "SELECT source_text, target_text, origin FROM translation_memory WHERE source_lang=? AND target_lang=? "
            "AND length(source_text) BETWEEN ? AND ?", (src, tgt, int(n * 0.6), int(n * 1.6) + 20)).fetchall()
        if not rows:
            return []
        choices = {i: strip_tags(r["source_text"]) for i, r in enumerate(rows)}
        found = process.extract(plain, choices, scorer=fuzz.ratio, limit=limit + 1, score_cutoff=FUZZY_THRESHOLD)
        out = []
        for _, score, i in found:
            if choices[i] == plain:
                continue
            r = rows[i]
            out.append(MemoryMatch(choices[i], strip_tags(r["target_text"]), r["origin"], score))
        return out[:limit]

    def store(self, src: str, tgt: str, source_text: str, target_text: str, model: str,
              origin: str = "model") -> None:
        if not self.enabled:
            return
        self.conn.execute(
            "INSERT INTO translation_memory(source_lang, target_lang, source_text, target_text, origin, model) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(source_lang, target_lang, source_text, origin) DO UPDATE SET "
            "target_text=excluded.target_text, model=excluded.model, created_at=datetime('now')",
            (src, tgt, source_text, target_text, origin, model))

    def commit(self) -> None:
        self.conn.commit()

    def count(self) -> int:
        return int(self.conn.execute("SELECT count(*) FROM translation_memory").fetchone()[0])

    def clear(self) -> int:
        n = self.count()
        self.conn.execute("DELETE FROM translation_memory")
        self.conn.commit()
        self.conn.execute("VACUUM")      # actually remove the text from the database file
        return n
