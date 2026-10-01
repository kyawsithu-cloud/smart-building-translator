"""Glossaries in the local database: CRUD, CSV import/export, and loading for translation."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sbt.settings import PROJECT_ROOT
from sbt.terminology.glossary import Glossary, Term, read_csv, write_csv

SEED_CSV = PROJECT_ROOT / "data" / "terminology" / "smart_building_en_ja.csv"
DEFAULT_GLOSSARY = "smart-building"
_COLS = "source_term, target_term, source_lang, target_lang, category, notes, do_not_translate, priority, context"


@dataclass(frozen=True)
class StoredTerm:
    id: int
    term: Term


class GlossaryRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- glossaries -------------------------------------------------------------------------------------
    def names(self) -> list[str]:
        return [r["name"] for r in self.conn.execute("SELECT name FROM glossaries ORDER BY name")]

    def ensure(self, name: str) -> int:
        """Return the glossary id, creating it. The default glossary is seeded from the project CSV once."""
        row = self.conn.execute("SELECT id FROM glossaries WHERE name = ?", (name,)).fetchone()
        if row:
            return int(row["id"])
        gid = int(self.conn.execute("INSERT INTO glossaries(name) VALUES (?)", (name,)).lastrowid or 0)
        if name == DEFAULT_GLOSSARY and SEED_CSV.exists():
            self._upsert_many(gid, read_csv(SEED_CSV))
        self.conn.commit()
        return gid

    def delete_glossary(self, name: str) -> bool:
        cur = self.conn.execute("DELETE FROM glossaries WHERE name = ?", (name,))
        self.conn.commit()
        return cur.rowcount > 0

    # --- terms ------------------------------------------------------------------------------------------
    def terms(self, name: str, search: str = "") -> list[StoredTerm]:
        gid = self.ensure(name)
        sql = f"SELECT id, {_COLS} FROM terminology WHERE glossary_id = ?"
        args: list[object] = [gid]
        if search:
            sql += " AND (source_term LIKE ? OR target_term LIKE ? OR category LIKE ?)"
            args += [f"%{search}%"] * 3
        rows = self.conn.execute(sql + " ORDER BY source_lang, lower(source_term), context", args)
        return [StoredTerm(r["id"], _term(r)) for r in rows]

    def add(self, name: str, term: Term) -> int:
        """Insert or update (same source term + languages + context)."""
        gid = self.ensure(name)
        self._upsert_many(gid, [term])
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM terminology WHERE glossary_id=? AND source_term=? AND source_lang=? AND target_lang=? "
            "AND context=?", (gid, term.source_term, term.source_lang, term.target_lang, term.context)).fetchone()
        return int(row["id"])

    def update(self, term_id: int, **changes: object) -> bool:
        allowed = set(_COLS.replace(" ", "").split(","))
        bad = set(changes) - allowed
        if bad:
            raise ValueError(f"Unknown field(s): {', '.join(sorted(bad))}")
        if "do_not_translate" in changes:
            changes["do_not_translate"] = 1 if changes["do_not_translate"] else 0
        sets = ", ".join(f"{k} = ?" for k in changes) + ", updated_at = datetime('now')"
        cur = self.conn.execute(f"UPDATE terminology SET {sets} WHERE id = ?", [*changes.values(), term_id])
        self.conn.commit()
        return cur.rowcount > 0

    def delete(self, term_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM terminology WHERE id = ?", (term_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def import_csv(self, name: str, path: Path) -> int:
        terms = read_csv(path)
        _validate(terms)
        self._upsert_many(self.ensure(name), terms)
        self.conn.commit()
        return len(terms)

    def export_csv(self, name: str, path: Path) -> int:
        terms = [st.term for st in self.terms(name)]
        write_csv(path, terms)
        return len(terms)

    def load(self, name: str) -> Glossary:
        return Glossary([st.term for st in self.terms(name)], name)

    def _upsert_many(self, gid: int, terms: list[Term]) -> None:
        self.conn.executemany(
            f"INSERT INTO terminology(glossary_id, {_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(glossary_id, source_term, source_lang, target_lang, context) DO UPDATE SET "
            "target_term=excluded.target_term, category=excluded.category, notes=excluded.notes, "
            "do_not_translate=excluded.do_not_translate, priority=excluded.priority, updated_at=datetime('now')",
            [(gid, t.source_term, t.target_term, t.source_lang, t.target_lang, t.category, t.notes,
              1 if t.do_not_translate else 0, t.priority, t.context) for t in terms])


def _term(r: sqlite3.Row) -> Term:
    return Term(r["source_term"], r["target_term"], r["source_lang"], r["target_lang"], r["category"], r["notes"],
                bool(r["do_not_translate"]), r["priority"], r["context"])


def _validate(terms: list[Term]) -> None:
    from sbt import languages
    for i, t in enumerate(terms, start=2):          # row 1 is the header
        for lang in (t.source_lang, t.target_lang):
            languages.get(lang)
        if not t.do_not_translate and not t.target_term:
            raise ValueError(f"Row {i}: target_term is empty (or mark the row do_not_translate)")
        if t.priority not in ("low", "normal", "high"):
            raise ValueError(f"Row {i}: priority must be low, normal or high")
