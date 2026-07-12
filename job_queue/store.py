"""
job_queue/store.py

A small SQLite-backed store for discovered jobs moving through:
  new -> scored -> drafted -> pending_review -> approved -> filled -> submitted
                                              \\-> rejected
                                              \\-> skipped

SQLite (not just JSON) because both the background search process and the
Streamlit review app need to read/write this concurrently without you
managing file locks yourself.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

VALID_STATUSES = {
    "new", "scored", "drafted", "pending_review",
    "approved", "rejected", "skipped", "filled", "submitted", "failed", "escalated",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT,
    is_remote       INTEGER DEFAULT 0,
    description     TEXT,
    tags            TEXT,           -- JSON-encoded list
    apply_url       TEXT NOT NULL,
    posted_at       TEXT,
    salary_text     TEXT,

    status          TEXT NOT NULL DEFAULT 'new',
    fit_score       INTEGER,         -- 0-100, set by the AI scorer
    fit_reasoning   TEXT,            -- short explanation from the AI scorer
    gaps_flagged    TEXT,            -- JSON list — honesty check vs achievement bank

    cv_draft_path        TEXT,
    cover_letter_path    TEXT,
    ai_engine_used        TEXT,      -- "claude" | "gemini"

    discovered_at   TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_fit_score ON jobs(fit_score);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobQueueStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # -----------------------------------------------------------------
    # Insertion (discovery layer calls this)
    # -----------------------------------------------------------------
    def upsert_job(self, job: dict[str, Any]) -> bool:
        """
        Insert a newly discovered job if it doesn't already exist.
        Returns True if it was newly inserted, False if it was a duplicate
        (duplicates are left untouched — we never overwrite review progress).
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT job_id FROM jobs WHERE job_id = ?", (job["job_id"],)
            ).fetchone()
            if existing:
                return False

            now = _now()
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, source, title, company, location, is_remote,
                    description, tags, apply_url, posted_at, salary_text,
                    status, discovered_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
                """,
                (
                    job["job_id"], job["source"], job["title"], job["company"],
                    job.get("location", ""), int(job.get("is_remote", False)),
                    job.get("description", ""), json.dumps(job.get("tags", [])),
                    job["apply_url"], job.get("posted_at", ""), job.get("salary_text"),
                    now, now,
                ),
            )
            return True

    # -----------------------------------------------------------------
    # Updates (scorer, tailoring engine, and review UI call these)
    # -----------------------------------------------------------------
    def update_status(self, job_id: str, status: str, notes: str | None = None) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_STATUSES}")
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ?, notes = COALESCE(?, notes) WHERE job_id = ?",
                (status, _now(), notes, job_id),
            )

    def set_score(self, job_id: str, fit_score: int, reasoning: str, gaps: list[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET fit_score = ?, fit_reasoning = ?, gaps_flagged = ?,
                    status = 'scored', updated_at = ?
                WHERE job_id = ?
                """,
                (fit_score, reasoning, json.dumps(gaps), _now(), job_id),
            )

    def set_draft(self, job_id: str, cv_path: str, cover_letter_path: str, ai_engine: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET cv_draft_path = ?, cover_letter_path = ?, ai_engine_used = ?,
                    status = 'pending_review', updated_at = ?
                WHERE job_id = ?
                """,
                (cv_path, cover_letter_path, ai_engine, _now(), job_id),
            )

    # -----------------------------------------------------------------
    # Reads (Streamlit review UI calls these)
    # -----------------------------------------------------------------
    def get_by_status(self, status: str, min_fit_score: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs WHERE status = ?"
        params: list[Any] = [status]
        if min_fit_score is not None:
            query += " AND (fit_score IS NULL OR fit_score >= ?)"
            params.append(min_fit_score)
        query += " ORDER BY fit_score DESC, discovered_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(r) for r in rows]


    def set_screenshot(self, job_id: str, screenshot_path: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET notes = COALESCE(notes,'') || ' | screenshot:' || ?, updated_at = ? WHERE job_id = ?",
                (screenshot_path, _now(), job_id),
            )
        # Also persist to a dedicated column if it exists; gracefully skip otherwise
        try:
            with self._connect() as conn:
                conn.execute("ALTER TABLE jobs ADD COLUMN screenshot_path TEXT")
        except Exception:
            pass
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET screenshot_path = ?, updated_at = ? WHERE job_id = ?",
                (screenshot_path, _now(), job_id),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            return self._row_to_dict(row) if row else None

    def get_all_jobs(
        self,
        status: str | None = None,
        source: str | None = None,
        search: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Flexible query for the dashboard's All Jobs tab."""
        query  = "SELECT * FROM jobs WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if source:
            query += " AND source = ?"
            params.append(source)
        if search:
            query += " AND (title LIKE ? OR company LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def approve_rejected(self, job_id: str) -> None:
        """Override poor-fit result: move rejected → approved for next pipeline run."""
        self.update_status(job_id, "approved", notes="⚡ Manually approved by Eddie")

    def save_cover_letter(self, job_id: str, text: str) -> None:
        """Persist an edited cover letter back into the notes field for display."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET notes = COALESCE(notes,'') || ' | cover_letter_saved=true', updated_at = ? WHERE job_id = ?",
                (_now(), job_id),
            )
        # Try to save to a cover_letter_text column (auto-migrates if missing)
        try:
            with self._connect() as conn:
                conn.execute("ALTER TABLE jobs ADD COLUMN cover_letter_text TEXT")
        except Exception:
            pass
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET cover_letter_text = ?, updated_at = ? WHERE job_id = ?",
                (text, _now(), job_id),
            )

    def get_sources(self) -> list[str]:
        """Return distinct source names for filter dropdowns."""
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT source FROM jobs ORDER BY source").fetchall()
            return [r["source"] for r in rows]

    def counts_by_status(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
            ).fetchall()
            return {r["status"]: r["cnt"] for r in rows}

    def counts_by_source(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source, COUNT(*) as cnt FROM jobs GROUP BY source"
            ).fetchall()
            return {r["source"]: r["cnt"] for r in rows}

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for json_field in ("tags", "gaps_flagged"):
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except (json.JSONDecodeError, TypeError):
                    d[json_field] = []
        return d


if __name__ == "__main__":
    # Quick smoke test
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        store = JobQueueStore(Path(tmp) / "test.sqlite3")

        sample_job = {
            "job_id": "abc123",
            "source": "remoteok",
            "title": "Remote Project Manager",
            "company": "TestCo",
            "location": "Worldwide",
            "is_remote": True,
            "description": "Test description",
            "tags": ["pm", "remote"],
            "apply_url": "https://example.com/job/1",
            "posted_at": "2026-06-20T00:00:00Z",
            "salary_text": "$60,000",
        }

        inserted = store.upsert_job(sample_job)
        print(f"Inserted: {inserted}")

        duplicate = store.upsert_job(sample_job)
        print(f"Duplicate insert blocked: {not duplicate}")

        store.set_score("abc123", fit_score=82, reasoning="Strong PM background match", gaps=["No formal PMP cert"])
        store.set_draft("abc123", "/path/cv.docx", "/path/cover.docx", "claude")

        pending = store.get_by_status("pending_review")
        print(f"Pending review: {len(pending)} job(s)")
        print(json.dumps(pending[0], indent=2, default=str))

        print(f"\nCounts by status: {store.counts_by_status()}")
