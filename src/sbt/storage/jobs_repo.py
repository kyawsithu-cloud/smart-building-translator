"""Job history: file names, counts and timings only — never document text."""
from __future__ import annotations

import sqlite3


class JobRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def record(self, report: dict[str, object]) -> None:
        self.conn.execute(
            "INSERT INTO translation_jobs(file_name, file_type, source_lang, target_lang, model, mode, segments, "
            "translated, warnings, seconds) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (report["file"], "pptx", report["source_lang"], report["target_lang"], report["model"],
             report["mode"], report["segments"], report["translated_segments"], len(report["issues"]),  # type: ignore[arg-type]
             report["seconds"]))
        self.conn.commit()

    def recent(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM translation_jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def clear(self) -> int:
        n = int(self.conn.execute("SELECT count(*) FROM translation_jobs").fetchone()[0])
        self.conn.execute("DELETE FROM translation_jobs")
        self.conn.commit()
        return n
