"""SQLite/libSQL persistence layer."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.utils import iso_now, json_dumps

try:  # pragma: no cover - optional dependency in local test envs.
    import libsql
except Exception:  # pragma: no cover
    libsql = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    config_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER,
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    text_content TEXT NOT NULL,
    summary TEXT NOT NULL,
    extracted_entities TEXT NOT NULL,
    extracted_roles TEXT NOT NULL,
    freshness_score REAL NOT NULL DEFAULT 0,
    relevance_score REAL NOT NULL DEFAULT 0,
    duplicate_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_id) REFERENCES sources(id)
);
CREATE INDEX IF NOT EXISTS idx_source_items_pub ON source_items(published_at);
CREATE INDEX IF NOT EXISTS idx_source_items_hash ON source_items(duplicate_hash);

CREATE TABLE IF NOT EXISTS extracted_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER NOT NULL,
    claim_text TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    supported INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(script_id) REFERENCES scripts(id)
);

CREATE TABLE IF NOT EXISTS content_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    slot_index INTEGER NOT NULL,
    scheduled_at TEXT NOT NULL,
    category TEXT NOT NULL,
    hook_style TEXT NOT NULL,
    title TEXT NOT NULL,
    angle TEXT NOT NULL,
    company TEXT NOT NULL,
    source_item_ids TEXT NOT NULL,
    freshness_score REAL NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(day, slot_index)
);

CREATE TABLE IF NOT EXISTS scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL,
    script_date TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    hook TEXT NOT NULL,
    beats_json TEXT NOT NULL,
    cta TEXT NOT NULL,
    full_script TEXT NOT NULL,
    caption TEXT NOT NULL,
    hashtags TEXT NOT NULL,
    source_notes TEXT NOT NULL,
    compliance_notes TEXT NOT NULL,
    fact_status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(topic_id) REFERENCES content_topics(id)
);
CREATE INDEX IF NOT EXISTS idx_scripts_date ON scripts(script_date);

CREATE TABLE IF NOT EXISTS media_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER NOT NULL,
    asset_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    provider TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(script_id) REFERENCES scripts(id)
);

CREATE TABLE IF NOT EXISTS render_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    output_path TEXT,
    audio_path TEXT,
    subtitle_path TEXT,
    duration_seconds REAL,
    fallback_used INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(script_id) REFERENCES scripts(id)
);

CREATE TABLE IF NOT EXISTS publish_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER NOT NULL,
    render_job_id INTEGER,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL,
    caption TEXT NOT NULL,
    media_url TEXT,
    instagram_creation_id TEXT,
    instagram_media_id TEXT,
    last_error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(script_id) REFERENCES scripts(id),
    FOREIGN KEY(render_job_id) REFERENCES render_jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_publish_jobs_sched ON publish_jobs(scheduled_at, status);

CREATE TABLE IF NOT EXISTS published_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publish_job_id INTEGER NOT NULL,
    script_id INTEGER NOT NULL,
    instagram_media_id TEXT NOT NULL,
    published_at TEXT NOT NULL,
    caption TEXT NOT NULL,
    hook TEXT NOT NULL,
    script_hash TEXT NOT NULL UNIQUE,
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(publish_job_id) REFERENCES publish_jobs(id),
    FOREIGN KEY(script_id) REFERENCES scripts(id)
);

CREATE TABLE IF NOT EXISTS post_insights (
    instagram_media_id TEXT PRIMARY KEY,
    script_id INTEGER,
    category TEXT,
    fetched_at TEXT NOT NULL,
    reach REAL DEFAULT 0,
    views REAL DEFAULT 0,
    saved REAL DEFAULT 0,
    shares REAL DEFAULT 0,
    likes REAL DEFAULT 0,
    comments REAL DEFAULT 0,
    avg_watch_ms REAL DEFAULT 0,
    skip_rate REAL,
    raw_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_date TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(metric_date, metric_name)
);
"""


class Database:
    """Small SQLite/libSQL helper with row-dict output."""

    def __init__(self, path: Path, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        requested_path = Path(path)
        if self.settings.use_turso and requested_path == self.settings.database_path:
            self.path = self.settings.database_runtime_path
        else:
            self.path = requested_path
        self._has_synced_replica = False
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def backend_name(self) -> str:
        return self.settings.database_backend

    def _open_connection(self) -> Any:
        if self.settings.use_turso:
            if libsql is None:
                raise RuntimeError(
                    "Turso is configured but the 'libsql' package is not installed. "
                    "Install project dependencies or unset TURSO_DATABASE_URL/TURSO_AUTH_TOKEN."
                )
            return libsql.connect(
                str(self.path),
                sync_url=self.settings.turso_database_url,
                auth_token=self.settings.turso_auth_token,
                sync_interval=self.settings.turso_sync_interval_seconds,
            )
        return sqlite3.connect(self.path)

    def _configure_connection(self, conn: Any) -> None:
        try:
            conn.row_factory = sqlite3.Row
        except Exception:
            pass
        conn.execute("PRAGMA foreign_keys=ON")
        if not self.settings.use_turso:
            conn.execute("PRAGMA journal_mode=WAL")

    def _maybe_sync(self, conn: Any, *, force: bool = False) -> None:
        if not self.settings.use_turso or not hasattr(conn, "sync"):
            return
        if force or not self._has_synced_replica:
            conn.sync()
            self._has_synced_replica = True

    def _column_names(self, cursor: Any) -> list[str]:
        description = getattr(cursor, "description", None) or []
        names: list[str] = []
        for column in description:
            if isinstance(column, (list, tuple)) and column:
                names.append(str(column[0]))
            elif column is not None:
                names.append(str(column))
        return names

    def _row_to_dict(self, row: Any, column_names: list[str] | None = None) -> dict[str, Any]:
        if row is None:
            return {}
        if isinstance(row, dict):
            return dict(row)
        try:
            return dict(row)
        except Exception:
            pass
        if hasattr(row, "keys"):
            try:
                return {key: row[key] for key in row.keys()}
            except Exception:
                pass
        if column_names and isinstance(row, (list, tuple)):
            return {name: row[index] for index, name in enumerate(column_names) if index < len(row)}
        raise TypeError(f"Unsupported database row type: {type(row)!r}")

    def _fetchone_dict(self, cursor: Any) -> dict[str, Any] | None:
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row, self._column_names(cursor))

    def _fetchall_dicts(self, cursor: Any) -> list[dict[str, Any]]:
        rows = cursor.fetchall()
        column_names = self._column_names(cursor)
        return [self._row_to_dict(row, column_names) for row in rows]

    @contextmanager
    def connect(self) -> Any:
        conn = self._open_connection()
        self._configure_connection(conn)
        self._maybe_sync(conn)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._maybe_sync(conn, force=True)

    def upsert_source(self, name: str, source_type: str, config: dict[str, Any]) -> int:
        now = iso_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sources(name, source_type, config_json, active, created_at, updated_at)
                VALUES(?, ?, ?, 1, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    source_type=excluded.source_type,
                    config_json=excluded.config_json,
                    updated_at=excluded.updated_at
                """,
                (name, source_type, json_dumps(config), now, now),
            )
            row = self._fetchone_dict(conn.execute("SELECT id FROM sources WHERE name = ?", (name,)))
            return int(row["id"])

    def source_item_exists(self, source_url: str, normalized_title: str, duplicate_hash: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM source_items
                WHERE source_url = ?
                   OR normalized_title = ?
                   OR duplicate_hash = ?
                LIMIT 1
                """,
                (source_url, normalized_title, duplicate_hash),
            ).fetchone()
            return row is not None

    def insert_source_item(
        self,
        source_id: int | None,
        payload: dict[str, Any],
    ) -> int | None:
        now = iso_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO source_items(
                    source_id, source_type, source_url, title, normalized_title, published_at,
                    fetched_at, text_content, summary, extracted_entities, extracted_roles,
                    freshness_score, relevance_score, duplicate_hash, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    payload["source_type"],
                    payload["source_url"],
                    payload["title"],
                    payload["normalized_title"],
                    payload.get("published_at"),
                    payload["fetched_at"],
                    payload["text_content"],
                    payload["summary"],
                    json_dumps(payload.get("extracted_entities", [])),
                    json_dumps(payload.get("extracted_roles", [])),
                    payload.get("freshness_score", 0),
                    payload.get("relevance_score", 0),
                    payload["duplicate_hash"],
                    json_dumps(payload.get("metadata", {})),
                    now,
                ),
            )
            return cursor.lastrowid or None

    def recent_source_items(self, days: int = 30, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM source_items
                WHERE datetime(created_at) >= datetime('now', ?)
                ORDER BY relevance_score DESC, freshness_score DESC, created_at DESC
                LIMIT ?
                """,
                (f"-{days} day", limit),
            )
            return self._fetchall_dicts(cursor)

    def source_items_by_ids(self, item_ids: list[int]) -> list[dict[str, Any]]:
        if not item_ids:
            return []
        placeholders = ", ".join("?" for _ in item_ids)
        with self.connect() as conn:
            cursor = conn.execute(
                f"SELECT * FROM source_items WHERE id IN ({placeholders})",
                item_ids,
            )
            return self._fetchall_dicts(cursor)

    def recent_scripts(self, days: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM scripts
                WHERE datetime(created_at) >= datetime('now', ?)
                ORDER BY created_at DESC
                """,
                (f"-{days} day",),
            )
            return self._fetchall_dicts(cursor)

    def scripts_for_day(self, day: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM scripts WHERE script_date = ? ORDER BY scheduled_at",
                (day,),
            )
            return self._fetchall_dicts(cursor)

    def script_by_id(self, script_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self._fetchone_dict(conn.execute("SELECT * FROM scripts WHERE id = ?", (script_id,)))

    def count_scripts_for_day(self, day: str) -> int:
        with self.connect() as conn:
            row = self._fetchone_dict(conn.execute(
                "SELECT COUNT(*) AS count FROM scripts WHERE script_date = ?",
                (day,),
            ))
            return int(row["count"])

    def insert_content_topic(self, payload: dict[str, Any]) -> int:
        now = iso_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO content_topics(
                    day, slot_index, scheduled_at, category, hook_style, title, angle,
                    company, source_item_ids, freshness_score, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day, slot_index) DO UPDATE SET
                    scheduled_at=excluded.scheduled_at,
                    category=excluded.category,
                    hook_style=excluded.hook_style,
                    title=excluded.title,
                    angle=excluded.angle,
                    company=excluded.company,
                    source_item_ids=excluded.source_item_ids,
                    freshness_score=excluded.freshness_score,
                    metadata_json=excluded.metadata_json
                """,
                (
                    payload["day"],
                    payload["slot_index"],
                    payload["scheduled_at"],
                    payload["category"],
                    payload["hook_style"],
                    payload["title"],
                    payload["angle"],
                    payload["company"],
                    json_dumps(payload["source_item_ids"]),
                    payload["freshness_score"],
                    json_dumps(payload.get("metadata", {})),
                    now,
                ),
            )
            row = self._fetchone_dict(conn.execute(
                """
                SELECT id FROM content_topics
                WHERE day = ? AND slot_index = ?
                """,
                (payload["day"], payload["slot_index"]),
            ))
            return int(row["id"])

    def insert_script(self, payload: dict[str, Any]) -> int:
        now = iso_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO scripts(
                    topic_id, script_date, scheduled_at, hook, beats_json, cta, full_script,
                    caption, hashtags, source_notes, compliance_notes, fact_status, evidence_json,
                    metadata_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["topic_id"],
                    payload["script_date"],
                    payload["scheduled_at"],
                    payload["hook"],
                    json_dumps(payload["beats"]),
                    payload["cta"],
                    payload["full_script"],
                    payload["caption"],
                    payload["hashtags"],
                    payload["source_notes"],
                    payload["compliance_notes"],
                    payload["fact_status"],
                    json_dumps(payload["evidence"]),
                    json_dumps(payload.get("metadata", {})),
                    payload.get("status", "planned"),
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def update_script_status(self, script_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE scripts SET status = ?, updated_at = ? WHERE id = ?",
                (status, iso_now(), script_id),
            )

    def insert_claim(self, script_id: int, claim_text: str, evidence: list[dict[str, Any]], supported: bool) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO extracted_claims(script_id, claim_text, evidence_json, supported, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (script_id, claim_text, json_dumps(evidence), int(supported), iso_now()),
            )

    def list_renderable_scripts(
        self,
        day: str | None = None,
        limit: int = 20,
        scheduled_before: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        query = """
            SELECT s.*, t.category, t.hook_style, t.company, t.angle
            FROM scripts s
            JOIN content_topics t ON s.topic_id = t.id
            WHERE s.status IN ('planned', 'render_failed')
              AND NOT EXISTS (
                  SELECT 1 FROM render_jobs r
                  WHERE r.script_id = s.id AND r.status = 'completed'
              )
        """
        if day:
            query += " AND s.script_date = ?"
            params.append(day)
        if scheduled_before:
            query += " AND s.scheduled_at <= ?"
            params.append(scheduled_before)
        query += " ORDER BY s.scheduled_at LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return self._fetchall_dicts(conn.execute(query, params))

    def insert_media_asset(self, script_id: int, asset_type: str, file_path: str, provider: str, metadata: dict[str, Any]) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO media_assets(script_id, asset_type, file_path, provider, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (script_id, asset_type, file_path, provider, json_dumps(metadata), iso_now()),
            )
            return int(cursor.lastrowid)

    def create_render_job(self, script_id: int, provider: str) -> int:
        now = iso_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO render_jobs(script_id, status, provider, metadata_json, created_at, updated_at)
                VALUES (?, 'running', ?, '{}', ?, ?)
                """,
                (script_id, provider, now, now),
            )
            return int(cursor.lastrowid)

    def complete_render_job(self, render_job_id: int, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE render_jobs
                SET status = 'completed',
                    provider = ?,
                    output_path = ?,
                    audio_path = ?,
                    subtitle_path = ?,
                    duration_seconds = ?,
                    fallback_used = ?,
                    metadata_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    payload["provider"],
                    payload["output_path"],
                    payload["audio_path"],
                    payload["subtitle_path"],
                    payload["duration_seconds"],
                    int(payload.get("fallback_used", False)),
                    json_dumps(payload.get("metadata", {})),
                    iso_now(),
                    render_job_id,
                ),
            )

    def fail_render_job(self, render_job_id: int, error: str, metadata: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE render_jobs
                SET status = 'failed', error = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (error, json_dumps(metadata or {}), iso_now(), render_job_id),
            )

    def create_publish_job(self, script_id: int, scheduled_at: str, caption: str) -> int:
        now = iso_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO publish_jobs(
                    script_id, scheduled_at, status, caption, metadata_json, created_at, updated_at
                ) VALUES (?, ?, 'planned', ?, '{}', ?, ?)
                """,
                (script_id, scheduled_at, caption, now, now),
            )
            return int(cursor.lastrowid)

    def mark_publish_job_ready(self, script_id: int, render_job_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE publish_jobs
                SET render_job_id = ?, status = 'ready', updated_at = ?
                WHERE script_id = ?
                """,
                (render_job_id, iso_now(), script_id),
            )

    def due_publish_jobs(self, now_iso: str, limit: int = 20, ignore_schedule: bool = False) -> list[dict[str, Any]]:
        query = """
            SELECT p.*, s.full_script, s.hook, s.source_notes, s.compliance_notes, s.scheduled_at AS script_scheduled_at,
                   r.output_path, r.audio_path, r.subtitle_path, r.metadata_json AS render_metadata_json,
                   (SELECT t.category FROM content_topics t WHERE t.id = s.topic_id) AS category
            FROM publish_jobs p
            JOIN scripts s ON p.script_id = s.id
            JOIN render_jobs r ON p.render_job_id = r.id
            WHERE p.status = 'ready'
        """
        params: list[Any] = []
        if not ignore_schedule:
            query += " AND p.scheduled_at <= ?"
            params.append(now_iso)
        query += " ORDER BY p.scheduled_at LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            return self._fetchall_dicts(conn.execute(query, params))

    def update_publish_job(self, publish_job_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = iso_now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [publish_job_id]
        with self.connect() as conn:
            conn.execute(
                f"UPDATE publish_jobs SET {assignments} WHERE id = ?",
                values,
            )

    def insert_published_post(
        self,
        publish_job_id: int,
        script_id: int,
        instagram_media_id: str,
        caption: str,
        hook: str,
        script_hash: str,
        metadata: dict[str, Any],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO published_posts(
                    publish_job_id, script_id, instagram_media_id, published_at,
                    caption, hook, script_hash, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    publish_job_id,
                    script_id,
                    instagram_media_id,
                    iso_now(),
                    caption,
                    hook,
                    script_hash,
                    json_dumps(metadata),
                ),
            )

    def posts_for_insights(self, days: int = 14) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT p.instagram_media_id, p.script_id, p.published_at,
                       (SELECT t.category FROM scripts s JOIN content_topics t ON t.id = s.topic_id WHERE s.id = p.script_id) AS category
                FROM published_posts p
                WHERE datetime(p.published_at) >= datetime('now', ?)
                  AND p.instagram_media_id NOT LIKE 'dryrun%'
                ORDER BY p.published_at DESC
                """,
                (f"-{days} day",),
            )
            return self._fetchall_dicts(cursor)

    def upsert_post_insights(self, row: dict[str, Any]) -> None:
        columns = ["instagram_media_id", "script_id", "category", "fetched_at", "reach", "views", "saved", "shares",
                   "likes", "comments", "avg_watch_ms", "skip_rate", "raw_json"]
        values = [row.get(column) for column in columns]
        with self.connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO post_insights({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                values,
            )

    def category_performance(self, days: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT category, COUNT(*) AS posts, SUM(reach) AS reach, SUM(saved) AS saved, SUM(shares) AS shares,
                       SUM(likes) AS likes, AVG(skip_rate) AS skip_rate
                FROM post_insights
                WHERE category IS NOT NULL AND datetime(fetched_at) >= datetime('now', ?)
                GROUP BY category
                """,
                (f"-{days} day",),
            )
            return self._fetchall_dicts(cursor)

    def recent_published_posts(self, days: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM published_posts
                WHERE datetime(published_at) >= datetime('now', ?)
                ORDER BY published_at DESC
                """,
                (f"-{days} day",),
            )
            return self._fetchall_dicts(cursor)

    def set_metric(self, metric_date: str, metric_name: str, metric_value: float, notes: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_metrics(metric_date, metric_name, metric_value, notes, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(metric_date, metric_name) DO UPDATE SET
                    metric_value=excluded.metric_value,
                    notes=excluded.notes
                """,
                (metric_date, metric_name, metric_value, notes, iso_now()),
            )

    def metrics_for_day(self, metric_date: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                SELECT metric_name, metric_value, notes
                FROM daily_metrics
                WHERE metric_date = ?
                ORDER BY metric_name
                """,
                (metric_date,),
            )
            return self._fetchall_dicts(cursor)
