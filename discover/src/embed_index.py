"""Build embeddings and keyword terms for Hacker News content."""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from typing import Any

import numpy as np

from . import util

LOGGER = logging.getLogger(__name__)
STOPWORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'aren\'t', 'as', 'at',
    'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by', 'can\'t', 'cannot', 'could',
    'couldn\'t', 'did', 'didn\'t', 'do', 'does', 'doesn\'t', 'doing', 'don\'t', 'down', 'during', 'each', 'few', 'for', 'from',
    'further', 'had', 'hadn\'t', 'has', 'hasn\'t', 'have', 'haven\'t', 'having', 'he', 'he\'d', 'he\'ll', 'he\'s', 'her', 'here',
    'here\'s', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'how\'s', 'i', 'i\'d', 'i\'ll', 'i\'m', 'i\'ve', 'if', 'in',
    'into', 'is', 'isn\'t', 'it', 'it\'s', 'its', 'itself', 'let\'s', 'me', 'more', 'most', 'mustn\'t', 'my', 'myself',
    'no', 'nor', 'not', 'of', 'off', 'on', 'once', 'only', 'or', 'other', 'ought', 'our', 'ours', 'ourselves', 'out',
    'over', 'own', 'same', 'shan\'t', 'she', 'she\'d', 'she\'ll', 'she\'s', 'should', 'shouldn\'t', 'so', 'some', 'such',
    'than', 'that', 'that\'s', 'the', 'their', 'theirs', 'them', 'themselves', 'then', 'there', 'there\'s', 'these',
    'they', 'they\'d', 'they\'ll', 'they\'re', 'they\'ve', 'this', 'those', 'through', 'to', 'too', 'under', 'until',
    'up', 'very', 'was', 'wasn\'t', 'we', 'we\'d', 'we\'ll', 'we\'re', 'we\'ve', 'were', 'weren\'t', 'what', 'what\'s',
    'when', 'when\'s', 'where', 'where\'s', 'which', 'while', 'who', 'who\'s', 'whom', 'why', 'why\'s', 'with', 'won\'t',
    'would', 'wouldn\'t', 'you', 'you\'d', 'you\'ll', 'you\'re', 'you\'ve', 'your', 'yours', 'yourself', 'yourselves',
    'http', 'https', 'www', 'com', 'org', 'net', 'io', 'dev', 'app', 'gov', 'edu', 'mil', 'co', 'uk', 'ca', 'de', 'fr',
    'using', 'based', 'make', 'new', 'data', 'code', 'like', 'just', 'get', 'one', 'also', 'use', 'time', 'work',
    'people', 'year', 'way', 'really', 'see', 'even', 'still', 'since', 'back', 'well', 'day', 'week', 'month',
    'thing', 'things', 'good', 'bad', 'great', 'want', 'need', 'know', 'think', 'say', 'said', 'told', 'asked',
    'issue', 'pull', 'request', 'open', 'closed', 'merged', 'commit', 'branch', 'release', 'version', 'update',
}


def _strip_markup(text: str) -> str:
    cleaned = re.sub(r'<[^>]+>', ' ', text)
    cleaned = re.sub(r'&[^;]+;', ' ', cleaned)
    cleaned = re.sub(r"\s+", ' ', cleaned)
    return cleaned.strip()


def _load_model(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "sentence_transformers is required for embedding support. Install it or run with --embed-model none."
        ) from exc
    return SentenceTransformer(model_name)


def _collect_objects(conn) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    
    # Collect Hacker News stories
    hn_query = (
        """
        SELECT s.id, s.title, COALESCE(s.url, '') AS url,
               COALESCE(GROUP_CONCAT(COALESCE(c.text, ''), ' '), '') AS comments
        FROM stories s
        LEFT JOIN comments c ON c.story_id = s.id
        GROUP BY s.id
        """
    )
    for row in conn.execute(hn_query):
        text_parts = [row['title'], row['url'], row['comments']]
        text = ' '.join(part for part in text_parts if part).strip()
        if not text:
            continue
        cleaned = _strip_markup(text)
        if cleaned:
            objects.append({'obj_type': 'story', 'obj_id': str(row['id']), 'text': cleaned})

    return objects


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if not norm:
        return vec
    return vec / norm


def _extract_terms(text: str, top_k: int = 12) -> dict[str, float]:
    tokens = re.findall(r"[A-Za-z0-9_]+", text.lower())
    filtered = [tok for tok in tokens if tok not in STOPWORDS and len(tok) > 2]
    counts = Counter(filtered)
    if not counts:
        return {}
    total = sum(counts.values())
    top = counts.most_common(top_k)
    return {term: freq / total for term, freq in top}


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


def build(conn, model_name: str) -> dict[str, int] | None:
    if not model_name or model_name.lower() == 'none':
        LOGGER.info("Skipping embedding build (model=%s)", model_name)
        with conn:
            conn.execute("DELETE FROM embeddings")
            conn.execute("DELETE FROM embedding_meta")
            conn.execute("DELETE FROM terms")
        return None

    objects = _collect_objects(conn)
    if not objects:
        LOGGER.info("No stories available for embedding")
        return {'embeddings': 0, 'terms': 0, 'removed': 0}

    meta_rows = conn.execute("SELECT obj_type, obj_id, text_hash FROM embedding_meta").fetchall()
    existing_meta = {(row['obj_type'], row['obj_id']): row['text_hash'] for row in meta_rows}

    targets: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for obj in objects:
        key = (obj['obj_type'], obj['obj_id'])
        text_hash = _hash_text(obj['text'])
        obj['text_hash'] = text_hash
        seen_keys.add(key)
        if existing_meta.get(key) != text_hash:
            targets.append(obj)

    removed_keys = [key for key in existing_meta if key not in seen_keys]
    if removed_keys:
        LOGGER.info("Removing %s obsolete embeddings", len(removed_keys))
        with conn:
            conn.executemany(
                "DELETE FROM embeddings WHERE obj_type = ? AND obj_id = ?",
                removed_keys,
            )
            conn.executemany(
                "DELETE FROM embedding_meta WHERE obj_type = ? AND obj_id = ?",
                removed_keys,
            )
            conn.executemany(
                "DELETE FROM terms WHERE obj_type = ? AND obj_id = ?",
                removed_keys,
            )

    if not targets:
        LOGGER.info("Embeddings already up-to-date")
        return {'embeddings': 0, 'terms': 0, 'removed': len(removed_keys)}

    if util.is_cancelled():
        raise util.CancelledError('Cancelled before embedding build')

    LOGGER.info("Encoding %s stories with model %s", len(targets), model_name)
    model = _load_model(model_name)
    batch_size = 64
    embedding_rows: list[tuple[str, str, int, bytes]] = []
    meta_rows: list[tuple[str, str, str, int]] = []
    term_rows: list[tuple[str, str, str, float]] = []
    stamp = util.epoch_now()
    dim: int | None = None

    for start in range(0, len(targets), batch_size):
        if util.is_cancelled():
            raise util.CancelledError('Cancelled during embedding build')
        batch = targets[start:start + batch_size]
        texts = [obj['text'] for obj in batch]
        vectors = model.encode(
            texts,
            convert_to_numpy=True,
            batch_size=min(32, len(batch)),
            show_progress_bar=False,
        )
        for obj, vec in zip(batch, vectors):
            arr = np.asarray(vec, dtype=np.float32)
            if dim is None:
                dim = int(arr.shape[0])
            normalized = _normalize(arr)
            embedding_rows.append(
                (
                    obj['obj_type'],
                    obj['obj_id'],
                    dim,
                    normalized.tobytes(),
                )
            )
            meta_rows.append(
                (
                    obj['obj_type'],
                    obj['obj_id'],
                    obj['text_hash'],
                    stamp,
                )
            )
            terms = _extract_terms(obj['text'])
            if terms:
                for term, weight in terms.items():
                    term_rows.append((term, obj['obj_type'], obj['obj_id'], float(weight)))

    if util.is_cancelled():
        raise util.CancelledError('Cancelled during embedding build')

    util.upsert_many(
        conn,
        """
        INSERT INTO embeddings (obj_type, obj_id, dim, vector)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(obj_type, obj_id) DO UPDATE SET
            dim=excluded.dim,
            vector=excluded.vector
        """,
        embedding_rows,
    )

    util.upsert_many(
        conn,
        """
        INSERT INTO embedding_meta (obj_type, obj_id, text_hash, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(obj_type, obj_id) DO UPDATE SET
            text_hash=excluded.text_hash,
            updated_at=excluded.updated_at
        """,
        meta_rows,
    )

    if term_rows:
        updated_pairs = list({(obj['obj_type'], obj['obj_id']) for obj in targets})
        with conn:
            conn.executemany(
                "DELETE FROM terms WHERE obj_type = ? AND obj_id = ?",
                updated_pairs,
            )
        util.upsert_many(
            conn,
            """
            INSERT INTO terms (term, obj_type, obj_id, weight)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(term, obj_type, obj_id) DO UPDATE SET
                weight=excluded.weight
            """,
            term_rows,
        )

    LOGGER.info(
        "Stored %s embedding vectors (%s terms, removed %s)",
        len(embedding_rows),
        len(term_rows),
        len(removed_keys),
    )
    return {
        'embeddings': len(embedding_rows),
        'terms': len(term_rows),
        'removed': len(removed_keys),
    }
