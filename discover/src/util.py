"""Shared utilities for the Discover module."""
from __future__ import annotations

import contextlib
import json
import logging

import sqlite3

import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import threading

LOGGER = logging.getLogger(__name__)


class CancelledError(Exception):
    """Raised when the discover run is cancelled."""
    pass

MODULE_ROOT = Path(__file__).resolve().parent
DB_DIR = MODULE_ROOT.parent / 'db'
_CANCEL_EVENT = threading.Event()
DB_PATH = DB_DIR / 'discover.sqlite'
SCHEMA_PATH = MODULE_ROOT / 'schema.sql'
VIEWS_PATH = MODULE_ROOT / 'views.sql'

_RUN_OBSERVER: Callable[[dict[str, Any]], None] | None = None
_STAGE_OBSERVER: Callable[[dict[str, Any]], None] | None = None


def set_run_observer(callback: Callable[[dict[str, Any]], None] | None) -> Callable[[dict[str, Any]], None] | None:
    global _RUN_OBSERVER
    previous = _RUN_OBSERVER
    _RUN_OBSERVER = callback
    return previous


def cancel_current_run() -> None:
    """Signal any running pipeline to stop."""
    _CANCEL_EVENT.set()


def reset_cancel_event() -> None:
    _CANCEL_EVENT.clear()


def is_cancelled() -> bool:
    return _CANCEL_EVENT.is_set()


def set_stage_observer(callback: Callable[[dict[str, Any]], None] | None) -> Callable[[dict[str, Any]], None] | None:
    global _STAGE_OBSERVER
    previous = _STAGE_OBSERVER
    _STAGE_OBSERVER = callback
    return previous


def _notify_run(event: dict[str, Any]) -> None:
    observer = _RUN_OBSERVER
    if observer is None:
        return
    try:
        observer(event)
    except Exception:
        LOGGER.debug('Run observer error', exc_info=True)


def _notify_stage(event: dict[str, Any]) -> None:
    observer = _STAGE_OBSERVER
    if observer is None:
        return
    try:
        observer(event)
    except Exception:
        LOGGER.debug('Stage observer error', exc_info=True)





def ensure_db_path() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)


def get_db() -> sqlite3.Connection:
    """Return a SQLite connection configured for the discover DB."""
    ensure_db_path()
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    conn.execute('PRAGMA journal_mode = WAL;')
    return conn


def _execute_script(conn: sqlite3.Connection, path: Path) -> None:
    sql = path.read_text(encoding='utf-8')
    with conn:
        conn.executescript(sql)




def _ensure_trend_schema(conn: sqlite3.Connection) -> None:
    def _has_column(table: str, column: str) -> bool:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if rows and hasattr(rows[0], 'keys'):
            return any(row['name'] == column for row in rows)
        return any(row[1] == column for row in rows)

    def _ensure_column(table: str, definition: str) -> None:
        column = definition.split()[0]
        if _has_column(table, column):
            return
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
        except sqlite3.OperationalError:
            pass

    with conn:
        _ensure_column('trend_clusters', 'fingerprint TEXT')
        _ensure_column('trend_clusters', 'latest_signal REAL NOT NULL DEFAULT 0')
        _ensure_column('trend_clusters', 'latest_delta REAL NOT NULL DEFAULT 0')
        _ensure_column('trend_clusters', 'latest_story_count INTEGER NOT NULL DEFAULT 0')
        _ensure_column('trend_clusters', 'latest_comment_count INTEGER NOT NULL DEFAULT 0')
        _ensure_column('trend_clusters', 'centroid BLOB')
        _ensure_column('trend_snapshots', 'comment_count INTEGER NOT NULL DEFAULT 0')
        _ensure_column('trend_snapshots', 'delta REAL NOT NULL DEFAULT 0')
        _ensure_column('trend_snapshots', 'signal REAL NOT NULL DEFAULT 0')

def ensure_schema(conn: sqlite3.Connection) -> None:
    _execute_script(conn, SCHEMA_PATH)
    _ensure_trend_schema(conn)


def ensure_views(conn: sqlite3.Connection) -> None:
    _execute_script(conn, VIEWS_PATH)


def epoch_now() -> int:
    return int(time.time())


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = (parsed.netloc or '').lower()
        if host.startswith('www.'):
            host = host[4:]
        return host or None
    except Exception:
        LOGGER.debug("Failed to parse domain from %s", url, exc_info=True)
        return None


@dataclass
class RunLog:
    since_arg: str
    embed_model: str
    status: str
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


@dataclass
class StageHandle:
    conn: sqlite3.Connection
    run_id: int
    stage_id: int
    stage_name: str

    def set_detail(self, detail: str) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE run_stage_logs SET detail = :detail WHERE stage_id = :id",
                {"detail": detail, "id": self.stage_id},
            )
        _notify_stage({
            'event': 'stage_detail',
            'run_id': self.run_id,
            'stage_id': self.stage_id,
            'stage': self.stage_name,
            'detail': detail,
        })


def log_run(conn: sqlite3.Connection, run: RunLog) -> int:
    params = {
        'started_at': run.started_at or iso_now(),
        'finished_at': run.finished_at,
        'status': run.status,
        'since_arg': run.since_arg,
        'embed_model': run.embed_model,
        'message': run.message,
    }
    with conn:
        cur = conn.execute(
            """
            INSERT INTO run_logs (started_at, finished_at, status, since_arg, embed_model, message)
            VALUES (:started_at, :finished_at, :status, :since_arg, :embed_model, :message)
            """,
            params,
        )
        return int(cur.lastrowid)


def update_run(conn: sqlite3.Connection, run_id: int, **updates: Any) -> None:
    if not updates:
        return
    columns = ', '.join(f"{col} = :{col}" for col in updates)
    params = dict(updates)
    params['id'] = run_id
    with conn:
        conn.execute(f"UPDATE run_logs SET {columns} WHERE id = :id", params)


@contextlib.contextmanager
def run_logger(conn: sqlite3.Connection, since_arg: str, embed_model: str) -> Iterator[int]:
    run_id = log_run(conn, RunLog(since_arg=since_arg, embed_model=embed_model, status='running'))
    _notify_run({
        'event': 'run_start',
        'run_id': run_id,
        'since': since_arg,
        'embed_model': embed_model,
    })
    try:
        yield run_id
    except CancelledError as exc:
        finished_at = iso_now()
        update_run(
            conn,
            run_id,
            status='cancelled',
            message=str(exc) if exc.args else 'cancelled',
            finished_at=finished_at,
        )
        _notify_run({
            'event': 'run_end',
            'run_id': run_id,
            'status': 'cancelled',
            'message': str(exc) if exc.args else 'cancelled',
            'finished_at': finished_at,
        })
        raise
    except Exception as exc:  # pragma: no cover - defensive
        finished_at = iso_now()
        update_run(
            conn,
            run_id,
            status='error',
            message=str(exc),
            finished_at=finished_at,
        )
        _notify_run({
            'event': 'run_end',
            'run_id': run_id,
            'status': 'error',
            'message': str(exc),
            'finished_at': finished_at,
        })
        raise
    else:
        finished_at = iso_now()
        update_run(
            conn,
            run_id,
            status='ok',
            finished_at=finished_at,
        )
        _notify_run({
            'event': 'run_end',
            'run_id': run_id,
            'status': 'ok',
            'finished_at': finished_at,
        })



@contextlib.contextmanager
def stage_logger(conn: sqlite3.Connection, run_id: int, stage: str, detail: str | None = None) -> Iterator[StageHandle]:
    started_at = iso_now()
    started = time.perf_counter()
    with conn:
        cur = conn.execute(
            """
            INSERT INTO run_stage_logs (run_id, stage, started_at, status, detail)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (run_id, stage, started_at, detail),
        )
        stage_id = int(cur.lastrowid)
    _notify_stage({
        'event': 'stage_start',
        'run_id': run_id,
        'stage_id': stage_id,
        'stage': stage,
        'detail': detail,
        'started_at': started_at,
    })
    handle = StageHandle(conn=conn, run_id=run_id, stage_id=stage_id, stage_name=stage)
    try:
        yield handle
    except CancelledError as exc:
        duration = time.perf_counter() - started
        finished_at = iso_now()
        with conn:
            conn.execute(
                """
                UPDATE run_stage_logs
                SET status = 'cancelled', finished_at = :finished_at, duration = :duration
                WHERE stage_id = :stage_id
                """
                ,
                {
                    'finished_at': finished_at,
                    'duration': duration,
                    'stage_id': stage_id,
                },
            )
        _notify_stage({
            'event': 'stage_cancelled',
            'run_id': run_id,
            'stage_id': stage_id,
            'stage': stage,
            'duration': duration,
            'finished_at': finished_at,
        })
        raise
    except Exception as exc:
        duration = time.perf_counter() - started
        finished_at = iso_now()
        with conn:
            conn.execute(
                """
                UPDATE run_stage_logs
                SET status = 'error', finished_at = :finished_at, duration = :duration,
                    detail = COALESCE(detail, '') || :suffix
                WHERE stage_id = :stage_id
                """,
                {
                    'finished_at': finished_at,
                    'duration': duration,
                    'suffix': f"\n{exc}",
                    'stage_id': stage_id,
                },
            )
        _notify_stage({
            'event': 'stage_error',
            'run_id': run_id,
            'stage_id': stage_id,
            'stage': stage,
            'duration': duration,
            'error': str(exc),
            'finished_at': finished_at,
        })
        raise
    else:
        duration = time.perf_counter() - started
        finished_at = iso_now()
        with conn:
            conn.execute(
                """
                UPDATE run_stage_logs
                SET status = 'ok', finished_at = :finished_at, duration = :duration
                WHERE stage_id = :stage_id
                """,
                {
                    'finished_at': finished_at,
                    'duration': duration,
                    'stage_id': stage_id,
                },
            )
        _notify_stage({
            'event': 'stage_end',
            'run_id': run_id,
            'stage_id': stage_id,
            'stage': stage,
            'duration': duration,
            'finished_at': finished_at,
        })


def get_source_state(conn: sqlite3.Connection, source: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT cursor FROM source_state WHERE source = ?",
        (source,),
    ).fetchone()
    if not row or row['cursor'] is None:
        return {}
    try:
        return json.loads(row['cursor'])
    except json.JSONDecodeError:
        LOGGER.warning("Corrupt cursor state for %s", source)
        return {}

CONFIG_PATH = DB_DIR.parent / 'discover_config.json'

def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config: dict[str, Any]) -> None:
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)


def save_source_state(conn: sqlite3.Connection, source: str, cursor: dict[str, Any]) -> None:
    payload = json.dumps(cursor)
    with conn:
        conn.execute(
            """
            INSERT INTO source_state (source, cursor, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                cursor = excluded.cursor,
                updated_at = excluded.updated_at
            """,
            (source, payload, iso_now()),
        )


def upsert_many(
    conn: sqlite3.Connection,
    sql: str,
    rows: Iterable[Iterable[Any]] | Iterable[dict[str, Any]],
) -> None:
    rows = list(rows)
    if not rows:
        return
    with conn:
        conn.executemany(sql, rows)


def chunked(iterable: Iterable[Any], size: int) -> Iterator[list[Any]]:
    chunk: list[Any] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def dump_debug_json(path: Path, payload: Any) -> None:
    try:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception:
        LOGGER.debug("Failed to dump debug json to %s", path, exc_info=True)


__all__ = [
    'DB_PATH',
    'RunLog',
    'StageHandle',
    'CancelledError',
    'cancel_current_run',
    'reset_cancel_event',
    'is_cancelled',
    'chunked',
    'domain_from_url',
    'dump_debug_json',
    'ensure_schema',
    'ensure_views',
    'epoch_now',
    'get_db',
    'get_source_state',
    'log_run',
    'run_logger',
    'save_source_state',
    'set_run_observer',
    'set_stage_observer',
    'stage_logger',
    'update_run',
    'upsert_many',
]
