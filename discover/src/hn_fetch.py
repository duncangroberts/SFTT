"""Fetch Hacker News stories and comments."""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any, Callable

import requests

from . import util

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://hacker-news.firebaseio.com/v0"
NEW_STORIES_ENDPOINT = f"{BASE_URL}/newstories.json"
ITEM_ENDPOINT = f"{BASE_URL}/item/{{item_id}}.json"
SESSION = requests.Session()


def _http_get_json(url: str) -> Any:
    resp = SESSION.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _fetch_item(item_id: int) -> dict[str, Any] | None:
    try:
        data = _http_get_json(ITEM_ENDPOINT.format(item_id=item_id))
        if not data:
            return None
        return data
    except Exception as exc:
        LOGGER.warning("Failed to fetch item %s: %s", item_id, exc)
        return None


def _iter_story_ids(limit: int = 2000) -> Iterable[int]:
    try:
        ids = _http_get_json(NEW_STORIES_ENDPOINT)
    except Exception as exc:
        LOGGER.error("Failed to fetch newstories: %s", exc)
        return []
    if not isinstance(ids, list):
        return []
    return ids[:limit]


def fetch_and_upsert(
    conn,
    since_unix: int,
    state: dict[str, Any] | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[dict[str, int], dict[str, Any]]:
    state = state or {}
    if progress_cb:
        progress_cb("starting...")
    last_ts = int(state.get('last_ts') or 0)
    cutoff_ts = max(since_unix, last_ts)

    LOGGER.info("Fetching Hacker News stories since %s (cutoff=%s)", since_unix, cutoff_ts)

    fetched_at = util.epoch_now()
    story_rows: list[tuple[Any, ...]] = []
    comment_rows: list[tuple[Any, ...]] = []
    max_seen_ts = last_ts
    stale_hits = 0

    for idx, story_id in enumerate(_iter_story_ids()):
        if util.is_cancelled():
            raise util.CancelledError('Cancelled during HN fetch')
        story = _fetch_item(int(story_id))
        if not story or story.get('type') != 'story':
            continue
        story_time = int(story.get('time', 0) or 0)
        if story_time <= cutoff_ts:
            stale_hits += 1
            if stale_hits > 40:
                break
            continue
        stale_hits = 0
        title = story.get('title') or ''
        url = story.get('url')
        domain = util.domain_from_url(url)
        story_rows.append(
            (
                story['id'],
                title,
                url,
                domain,
                story.get('by'),
                story_time,
                story.get('score'),
                story.get('descendants'),
                fetched_at,
            )
        )
        if progress_cb and len(story_rows) % 10 == 0:
            progress_cb(f"stories={len(story_rows)}")
        max_seen_ts = max(max_seen_ts, story_time)
        kids = story.get('kids') or []
        for kid_id in kids[:20]:
            if util.is_cancelled():
                raise util.CancelledError('Cancelled during HN comment fetch')
            comment = _fetch_item(int(kid_id))
            if not comment or comment.get('type') != 'comment':
                continue
            comment_rows.append(
                (
                    comment['id'],
                    comment.get('parent'),
                    comment.get('by'),
                    comment.get('time'),
                    comment.get('text'),
                    story['id'],
                )
            )
            if progress_cb and len(comment_rows) % 20 == 0:
                progress_cb(f"comments={len(comment_rows)}")
        if idx % 50 == 0:
            time.sleep(0.2)
        else:
            time.sleep(0.05)

    if story_rows:
        util.upsert_many(
            conn,
            """
            INSERT INTO stories (id, title, url, domain, by, time, score, descendants, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                url=excluded.url,
                domain=excluded.domain,
                by=excluded.by,
                time=excluded.time,
                score=excluded.score,
                descendants=excluded.descendants,
                fetched_at=excluded.fetched_at
            """,
            story_rows,
        )
    if comment_rows:
        util.upsert_many(
            conn,
            """
            INSERT INTO comments (id, parent, by, time, text, story_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                parent=excluded.parent,
                by=excluded.by,
                time=excluded.time,
                text=excluded.text,
                story_id=excluded.story_id
            """,
            comment_rows,
        )

    if progress_cb:
        progress_cb(f"stories={len(story_rows)}, comments={len(comment_rows)}")
    LOGGER.info("Stored %s stories and %s comments", len(story_rows), len(comment_rows))
    cursor = {'last_ts': max_seen_ts}
    return {'stories': len(story_rows), 'comments': len(comment_rows)}, cursor
