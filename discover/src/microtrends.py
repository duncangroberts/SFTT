"Build trend clusters and track emerging signals from Hacker News."
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np

from . import util

LOGGER = logging.getLogger(__name__)


@dataclass
class _ClusterScratch:
    sum_vector: np.ndarray
    members: list[int] = field(default_factory=list)
    story_ids: list[str] = field(default_factory=list)

    def add_member(self, idx: int, obj_id: str, vector: np.ndarray) -> None:
        self.members.append(idx)
        self.story_ids.append(obj_id)
        self.sum_vector += vector

    @property
    def centroid(self) -> np.ndarray:
        norm = np.linalg.norm(self.sum_vector)
        if not norm:
            return self.sum_vector
        return self.sum_vector / norm


from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

def _load_embeddings(conn, cutoff_unix: int, window_days: int, comment_weight: float, sentiment_weight: float) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.obj_type,
               e.obj_id,
               e.vector,
               v.ts_unix,
               v.metric_1,
               v.metric_2,
               v.title_or_name,
               (SELECT metric_1 FROM v_items v2 WHERE v2.obj_id = v.obj_id AND v2.ts_unix < v.ts_unix ORDER BY v2.ts_unix DESC LIMIT 1) as prev_metric_1,
               (SELECT metric_2 FROM v_items v2 WHERE v2.obj_id = v.obj_id AND v2.ts_unix < v.ts_unix ORDER BY v2.ts_unix DESC LIMIT 1) as prev_metric_2
        FROM embeddings e
        JOIN v_items v ON v.obj_type = e.obj_type AND v.obj_id = e.obj_id
        WHERE v.ts_unix >= ?
        """,
        (cutoff_unix,),
    ).fetchall()
    items: list[dict[str, Any]] = []
    now = util.epoch_now()
    analyzer = SentimentIntensityAnalyzer()
    for row in rows:
        vec = np.frombuffer(row['vector'], dtype=np.float32)
        item_ts = int(row['ts_unix'] or 0)
        score = float(row['metric_1'] or 0)
        comments = float(row['metric_2'] or 0)
        title = row['title_or_name']
        prev_score = float(row['prev_metric_1'] or 0)
        prev_comments = float(row['prev_metric_2'] or 0)

        # Calculate velocity
        velocity = (score - prev_score) + (comments - prev_comments) * comment_weight

        # Sentiment analysis
        sentiment = analyzer.polarity_scores(title)['compound']
        
        weight = _signal_weight(now, item_ts, window_days)
        base_signal = score + comment_weight * comments + 1.0 + sentiment * sentiment_weight + velocity
        signal = base_signal * weight

        items.append(
            {
                'obj_type': row['obj_type'],
                'obj_id': row['obj_id'],
                'vector': vec,
                'ts_unix': item_ts,
                'score': score,
                'comments': comments,
                'title': title,
                'signal': signal,
                'sentiment': sentiment,
                'velocity': velocity,
            }
        )
    
    # Sort by signal to prioritize important items for clustering
    items.sort(key=lambda item: item['signal'], reverse=True)
    
    # Return all items, not just the top N
    return items


def _load_terms(conn) -> dict[tuple[str, str], dict[str, float]]:
    mapping: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in conn.execute("SELECT term, obj_type, obj_id, weight FROM terms"):
        mapping[(row['obj_type'], row['obj_id'])][row['term']] = row['weight']
    return mapping


def _signal_weight(now: int, item_ts: int, window_days: int) -> float:
    if item_ts <= 0:
        return 0.0
    age_seconds = max(0, now - item_ts)
    half_life_days = max(window_days / 2.0, 1.5)
    decay_constant = half_life_days * 86400.0
    return math.exp(-age_seconds / decay_constant)


def _build_clusters(items: list[dict[str, Any]], threshold: float) -> list[_ClusterScratch]:
    clusters: list[_ClusterScratch] = []
    for idx, item in enumerate(items):
        if util.is_cancelled():
            raise util.CancelledError('Cancelled before trend clustering')
        best_idx: int | None = None
        best_score = threshold
        vec = item['vector']
        for cluster_idx, cluster in enumerate(clusters):
            sim = float(np.dot(vec, cluster.centroid))
            if sim >= threshold and sim > best_score:
                best_idx = cluster_idx
                best_score = sim
        if best_idx is None:
            clusters.append(_ClusterScratch(sum_vector=vec.copy(), members=[idx], story_ids=[item['obj_id']]))
        else:
            clusters[best_idx].add_member(idx, item['obj_id'], vec)
    return clusters

def _top_terms_for_cluster(cluster_members: list[int], items: list[dict[str, Any]], term_map: dict[tuple[str, str], dict[str, float]], top_k: int = 6) -> tuple[list[str], str, list[str]]:
    counter: dict[str, float] = defaultdict(float)
    titles: list[str] = []
    for idx in cluster_members:
        item = items[idx]
        titles.append(item['title'])
        terms = term_map.get((item['obj_type'], item['obj_id']), {})
        for term, weight in terms.items():
            counter[term] += weight
    if not counter:
        titles = titles[:5]
        raw_label = ' / '.join(titles[:2]) or 'Untitled'
        return [], raw_label, titles
    top_terms = sorted(counter.items(), key=lambda entry: entry[1], reverse=True)[:top_k]
    keywords = [term for term, _ in top_terms]
    label = ' / '.join(term.replace('_', ' ').title() for term in keywords[:3]) or keywords[0]
    return keywords, label, titles[:5]


def _llm_summarise(titles: list[str], comments: list[str], use_llm: bool, progress_cb: Callable[[str], None] | None = None) -> str | None:
    if not use_llm:
        return None
    if not (titles or comments):
        if progress_cb:
            progress_cb('LLM summarisation skipped: no titles or comments')
        return None

    if progress_cb:
        progress_cb(f'Attempting to summarise with LLM. Titles: {len(titles)}, Comments: {len(comments)}')

    try:
        from llm_client import LLMClientError
        from llm_runtime import LlamaServerManager
    except Exception:  # pragma: no cover - optional dependency
        if progress_cb:
            progress_cb('LLM runtime unavailable for trend labels')
        return None

    manager = LlamaServerManager()
    prompt_titles = '\n'.join(f"- {title}" for title in titles[:8])
    prompt_comments = '\n'.join(f'- \"{c[:200]}...\"' for c in comments[:10])

    prompt = (
        "You are an analyst identifying emerging technology trends from Hacker News."
        "Based on the provided story titles and comments, please generate the following:"
        "1. A short, descriptive title for the theme (4-6 words)."
        "2. A brief summary of why this theme is interesting to a technology analyst."
        f"Titles:\n{prompt_titles}\n\n"
        f"Comments:\n{prompt_comments}\n\n"
        "Title:"
    )
    try:
        with manager.ensure_running(progress_cb) as server:
            raw = server.client.generate(
                prompt,
                system_prompt="You create short trend labels.",
                max_tokens=32,
            )
    except LLMClientError as exc:  # pragma: no cover - runtime dependent
        if progress_cb:
            progress_cb(f'LLM label request failed: {exc}')
        return None
    label = raw.strip()
    title = ""
    summary = ""
    try:
        lines = label.split('\n')
        if len(lines) >= 2:
            title = lines[0].replace("Title:", "").strip()
            summary = lines[1].replace("Summary:", "").strip()
        else:
            title = lines[0].replace("Title:", "").strip()
    except:
        pass # Fallback to using the whole response as the label

    return title, summary

def _llm_filter_hot_terms(terms: list[str], use_llm: bool, progress_cb: Callable[[str], None] | None = None) -> list[str]:
    if not use_llm or not terms:
        return terms
    try:
        from llm_client import LLMClientError
        from llm_runtime import LlamaServerManager
    except Exception:
        if progress_cb:
            progress_cb('LLM runtime unavailable for term filtering')
        return terms

    manager = LlamaServerManager()
    prompt_terms = ', '.join(terms)
    prompt = (
        "You are an analyst identifying emerging technology trends. "
        "From the following list of 'hot terms' from Hacker News, filter out any that are generic, common, or otherwise uninteresting for technology trend analysis. "
        "Examples to remove: 'show hn', 'ask hn', 'pdf', '2024', 'google', 'apple', 'microsoft', 'amazon', 'facebook', 'data', 'using', 'release', 'video'.\n"
        f"Terms: {prompt_terms}\n\n"
        "Return a comma-separated list of the interesting terms."
    )
    try:
        with manager.ensure_running(progress_cb) as server:
            raw = server.client.generate(
                prompt,
                system_prompt="You are a helpful assistant that filters lists of terms.",
                max_tokens=1024,
            )
    except LLMClientError as exc:
        if progress_cb:
            progress_cb(f'LLM term filtering request failed: {exc}')
        return terms
    
    filtered_terms = [term.strip() for term in raw.strip().split(',') if term.strip()]
    if progress_cb:
        progress_cb(f'{len(filtered_terms)} hot terms remain after LLM filtering')
    return filtered_terms

def _fingerprint(keywords: list[str], story_ids: list[str]) -> str:
    if keywords:
        return '|'.join(sorted(keywords[:3]))
    return '|'.join(sorted(story_ids[:2]))


def _ensure_cluster_members_table(conn, trend_id: int, member_keys: set[str], today: str) -> None:
    for key in member_keys:
        obj_type, obj_id = key.split(':', 1)
        with conn:
            conn.execute(
                """
                INSERT INTO trend_cluster_members (trend_id, obj_type, obj_id, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(trend_id, obj_type, obj_id) DO UPDATE SET
                    last_seen = excluded.last_seen
                """,
                (
                    trend_id,
                    obj_type,
                    obj_id,
                    today,
                    today,
                ),
            )


def _calculate_term_surges(conn, run_id: int, since_unix: int, window_days: int, use_llm: bool = False, progress_cb: Callable[[str], None] | None = None) -> None:
    if progress_cb:
        progress_cb("Calculating term surges...")
    lookback = window_days * 86400
    previous_start = max(0, since_unix - lookback)
    now_iso = util.iso_now()

    current_rows = conn.execute(
        """
        SELECT t.term,
               SUM(t.weight * (COALESCE(s.score, 0) + 1)) AS score
        FROM terms t
        JOIN stories s ON t.obj_type = 'story' AND t.obj_id = CAST(s.id AS TEXT)
        WHERE s.time >= ?
        GROUP BY t.term
        """,
        (since_unix,),
    ).fetchall()
    previous_rows = conn.execute(
        """
        SELECT t.term,
               SUM(t.weight * (COALESCE(s.score, 0) + 1)) AS score
        FROM terms t
        JOIN stories s ON t.obj_type = 'story' AND t.obj_id = CAST(s.id AS TEXT)
        WHERE s.time >= ? AND s.time < ?
        GROUP BY t.term
        """,
        (previous_start, since_unix),
    ).fetchall()

    current = {row['term']: float(row['score'] or 0.0) for row in current_rows if row['score']}
    previous = {row['term']: float(row['score'] or 0.0) for row in previous_rows if row['score']}

    if not current:
        with conn:
            conn.execute("DELETE FROM term_surge_snapshots WHERE run_id = ?", (run_id,))
        return

    surges: list[tuple[str, float, float, float, float]] = []
    for term, score in current.items():
        baseline = previous.get(term, 0.0)
        if score < 1.0:
            continue
        ratio = score / (baseline + 1.0)
        delta = score - baseline
        surges.append((term, score, baseline, ratio, delta))

    surges.sort(key=lambda entry: entry[3], reverse=True)
    top_surges = surges[:20]

    if use_llm:
        top_terms = [s[0] for s in top_surges]
        if progress_cb:
            progress_cb(f'Filtering {len(top_terms)} hot terms with LLM')
        filtered_terms = _llm_filter_hot_terms(top_terms, use_llm, progress_cb)
        top_surges = [s for s in top_surges if s[0] in filtered_terms]

    with conn:
        conn.execute("DELETE FROM term_surge_snapshots WHERE run_id = ?", (run_id,))
        conn.executemany(
            """
            INSERT INTO term_surge_snapshots (run_id, term, current_score, baseline_score, surge_ratio, surge_delta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    term,
                    current_score,
                    baseline_score,
                    ratio,
                    delta,
                    now_iso,
                )
                for term, current_score, baseline_score, ratio, delta in top_surges
            ],
        )

from .util import load_config

def _store_trend_history(conn, run_id: int) -> None:
    """Store a snapshot of the trend data for each run."""
    trends = conn.execute("SELECT trend_id, latest_signal, latest_sentiment FROM trend_clusters WHERE active = 1").fetchall()
    with conn:
        for trend in trends:
            conn.execute(
                """
                INSERT INTO trend_history (trend_id, run_id, signal, sentiment)
                VALUES (?, ?, ?, ?)
                """,
                (trend['trend_id'], run_id, trend['latest_signal'], trend['latest_sentiment'])
            )

def _split_theme(conn, trend_id: int, sim_threshold: float) -> list[int]:
    """Split a broad theme into smaller, more coherent sub-themes."""
    # Get the stories in the broad theme
    stories = conn.execute("SELECT obj_id FROM trend_cluster_members WHERE trend_id = ?", (trend_id,)).fetchall()
    story_ids = [row['obj_id'] for row in stories]

    # Get the full item details for the stories
    rows = conn.execute(f"SELECT obj_type, obj_id, vector, ts_unix, metric_1, metric_2, title_or_name FROM v_items WHERE obj_id IN ({','.join(['?']*len(story_ids))})", story_ids).fetchall()
    items = []
    for row in rows:
        items.append({
            'obj_type': row['obj_type'],
            'obj_id': row['obj_id'],
            'vector': np.frombuffer(row['vector'], dtype=np.float32),
            'ts_unix': row['ts_unix'],
            'score': row['metric_1'],
            'comments': row['metric_2'],
            'title': row['title_or_name'],
            'signal': 0, # This will be recalculated later if needed
            'sentiment': 0, # This will be recalculated later if needed
        })

    # Re-cluster the stories with a higher similarity threshold
    clusters = _build_clusters(items, sim_threshold * 1.1) # Increase threshold by 10%

    # Create new themes for the sub-clusters
    new_trend_ids = []
    for cluster in clusters:
        if len(cluster.members) < 2:
            continue
        
        # Calculate centroid for the new sub-theme
        sub_theme_vectors = [items[idx]['vector'] for idx in cluster.members]
        sub_theme_centroid = np.mean(sub_theme_vectors, axis=0)

        # Create a new theme
        with conn:
            cur = conn.execute("INSERT INTO trend_clusters (centroid, active) VALUES (?, 1)", (sub_theme_centroid.tobytes(),))
            new_trend_id = int(cur.lastrowid)
            new_trend_ids.append(new_trend_id)

            # Add members to the new theme
            member_keys = {f"story:{items[idx]['obj_id']}" for idx in cluster.members}
            _ensure_cluster_members_table(conn, new_trend_id, member_keys, datetime.now(timezone.utc).date().isoformat())

    # Mark the broad theme as inactive
    with conn:
        conn.execute("UPDATE trend_clusters SET active = 0 WHERE trend_id = ?", (trend_id,))

    return new_trend_ids


def _calculate_cluster_variance(conn, trend_id: int) -> float:
    """Calculate the variance of the story vectors within a cluster."""
    rows = conn.execute("SELECT vector FROM embeddings WHERE obj_id IN (SELECT obj_id FROM trend_cluster_members WHERE trend_id = ?)", (trend_id,)).fetchall()
    if not rows:
        return 0.0
    
    vectors = [np.frombuffer(row['vector'], dtype=np.float32) for row in rows]
    if len(vectors) < 2:
        return 0.0

    centroid = np.mean(vectors, axis=0)
    variance = np.mean([np.linalg.norm(v - centroid) for v in vectors])
    return variance


def _merge_themes(conn, trend_id1: int, trend_id2: int) -> int:
    """Merge two themes into a new one."""
    # Get the two themes
    t1 = conn.execute("SELECT * FROM trend_clusters WHERE trend_id = ?", (trend_id1,)).fetchone()
    t2 = conn.execute("SELECT * FROM trend_clusters WHERE trend_id = ?", (trend_id2,)).fetchone()

    # Create a new theme
    new_label = t1['canonical_label'] + " / " + t2['canonical_label']
    new_centroid = (np.frombuffer(t1['centroid'], dtype=np.float32) + np.frombuffer(t2['centroid'], dtype=np.float32)) / 2
    
    with conn:
        cur = conn.execute(
            """
            INSERT INTO trend_clusters (canonical_label, centroid, active)
            VALUES (?, ?, 1)
            """,
            (new_label, new_centroid.tobytes()),
        )
        new_trend_id = int(cur.lastrowid)

        # Update members to point to the new trend_id
        conn.execute("UPDATE trend_cluster_members SET trend_id = ? WHERE trend_id = ?", (new_trend_id, trend_id1))
        conn.execute("UPDATE trend_cluster_members SET trend_id = ? WHERE trend_id = ?", (new_trend_id, trend_id2))

        # Mark old themes as inactive
        conn.execute("UPDATE trend_clusters SET active = 0 WHERE trend_id = ?", (trend_id1,))
        conn.execute("UPDATE trend_clusters SET active = 0 WHERE trend_id = ?", (trend_id2,))

    return new_trend_id


def _calculate_theme_similarity(conn, trend_id1: int, trend_id2: int) -> float:
    """Calculate the cosine similarity between two themes based on their centroids."""
    c1_row = conn.execute("SELECT centroid FROM trend_clusters WHERE trend_id = ?", (trend_id1,)).fetchone()
    c2_row = conn.execute("SELECT centroid FROM trend_clusters WHERE trend_id = ?", (trend_id2,)).fetchone()
    if not c1_row or not c2_row:
        return 0.0
    
    c1 = np.frombuffer(c1_row['centroid'], dtype=np.float32) if c1_row['centroid'] else None
    c2 = np.frombuffer(c2_row['centroid'], dtype=np.float32) if c2_row['centroid'] else None

    if c1 is None or c2 is None:
        return 0.0

    dot_product = np.dot(c1, c2)
    norm_c1 = np.linalg.norm(c1)
    norm_c2 = np.linalg.norm(c2)

    if norm_c1 == 0 or norm_c2 == 0:
        return 0.0

    return dot_product / (norm_c1 * norm_c2)


class Microtrends:
    def __init__(self, db_path: str, llm_client: Any | None = None) -> None:
        self.db_path = db_path
        self.llm_client = llm_client

    def _get_llm_label_for_cluster(self, cluster_data: list[dict[str, Any]]) -> tuple[str | None, str | None]:
        if not self.llm_client:
            return None, None

        titles = []
        for item in cluster_data:
            title = item.get('title')
            if title:
                titles.append(title)
        if not titles:
            return None, None

        prompt = (
            'Summarize the following titles into a concise, single-phrase label and a brief summary\n\n'
            + '\n'.join(titles)
        )
        system_prompt = (
            'You are a helpful assistant that summarizes topics into concise labels and summaries. ' 
            'Respond with only the label on the first line and the summary on the second line, no extra commentary.'
        )

        try:
            response = self.llm_client.generate(
                prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=100,
                stop=['\n\n'],
            )
        except Exception as exc:  # pragma: no cover - depends on runtime LLM
            LOGGER.exception('Error generating LLM label: %s', exc)
            return None, None

        lines = response.strip().split('\n', 1)
        label = lines[0].strip() if lines else None
        summary = lines[1].strip() if len(lines) > 1 else None
        return label, summary

    def build_components(
        self,
        conn,
        run_id: int,
        cutoff_unix: int,
        *,
        window_days: int = 30,
        progress_cb: Callable[[str], None] | None = None,
    ) -> dict[str, int]:
        config = load_config()
        comment_weight = config.get('comment_weight', 0.6)
        sim_threshold = config.get('sim_threshold', 0.78)
        stale_decay_factor = config.get('stale_decay_factor', 0.9)
        sentiment_weight = config.get('sentiment_weight', 0.5)
        use_llm_labels = bool(self.llm_client)
    
        if progress_cb:
            progress_cb(f'build_components called with use_llm_labels={use_llm_labels}')
        
        if progress_cb:
            progress_cb("Loading embeddings...")
        items = _load_embeddings(conn, cutoff_unix, window_days, comment_weight, sentiment_weight)
        if not items:
            LOGGER.info("No embeddings available for trend detection; run the embedding stage first")
            if progress_cb:
                progress_cb("No embeddings available for trend detection; run the embedding stage first")
            return {'trends': 0, 'new_trends': 0, 'updated_trends': 0}
    
        if util.is_cancelled():
            raise util.CancelledError('Cancelled before micro-trend build')
    
        if progress_cb:
            progress_cb(f"Building clusters with threshold={sim_threshold}...")
        clusters = _build_clusters(items, sim_threshold)
        if progress_cb:
            progress_cb(f"Found {len(clusters)} clusters.")
    
        # Create trend clusters in the database
        for cluster in clusters:
            if len(cluster.members) < 2:
                continue
            
            with conn:
                cur = conn.execute("INSERT INTO trend_clusters (active) VALUES (1)")
                trend_id = int(cur.lastrowid)
                member_keys = {f"story:{items[idx]['obj_id']}" for idx in cluster.members}
                _ensure_cluster_members_table(conn, trend_id, member_keys, datetime.now(timezone.utc).date().isoformat())
    
        # Merge similar clusters
        merge_threshold = config.get('merge_threshold', 0.9)
        trends = conn.execute("SELECT trend_id FROM trend_clusters WHERE active = 1").fetchall()
        trend_ids = [t['trend_id'] for t in trends]
        merged_trends = set()
        for i in range(len(trend_ids)):
            if i in merged_trends:
                continue
            for j in range(i + 1, len(trend_ids)):
                if j in merged_trends:
                    continue
                
                t1_id = trend_ids[i]
                t2_id = trend_ids[j]
    
                similarity = _calculate_theme_similarity(conn, t1_id, t2_id)
                if similarity > merge_threshold:
                    if progress_cb:
                        progress_cb(f"Merging clusters {t1_id} and {t2_id} with similarity {similarity:.2f}")
                    new_trend_id = _merge_themes(conn, t1_id, t2_id)
                    merged_trends.add(i)
                    merged_trends.add(j)
                    trend_ids.append(new_trend_id) # Add the new cluster to the list
                    break # Move to the next cluster
    
        # Split broad themes
        split_threshold = config.get('split_threshold', 0.2)
        trends = conn.execute("SELECT trend_id FROM trend_clusters WHERE active = 1").fetchall()
        trend_ids = [t['trend_id'] for t in trends]
        split_themes = set()
        newly_created_themes = []
        for i, trend_id in enumerate(trend_ids):
            if i in split_themes:
                continue
            
            variance = _calculate_cluster_variance(conn, trend_id)
            if variance > split_threshold:
                if progress_cb:
                    progress_cb(f"Splitting theme {trend_id} with variance {variance:.2f}")
                new_trend_ids = _split_theme(conn, trend_id, sim_threshold)
                split_themes.add(i)
                newly_created_themes.extend(new_trend_ids)
    
        term_map = _load_terms(conn)
        now = util.epoch_now()
        today = datetime.now(timezone.utc).date().isoformat()
        window_weeks = max(window_days / 7.0, 1.0)
    
        # Get active clusters from the database
        clusters = conn.execute("SELECT trend_id FROM trend_clusters WHERE active = 1").fetchall()
    
        cluster_rows = conn.execute(
            "SELECT * FROM trend_clusters"
        ).fetchall()
        cluster_meta = {row['trend_id']: dict(row) for row in cluster_rows}
        existing_by_fp = {row['fingerprint']: dict(row) for row in cluster_rows if row['fingerprint']}
    
        existing_member_sets: dict[int, set[str]] = {}
        for row in conn.execute(
            "SELECT trend_id, obj_type, obj_id FROM trend_cluster_members"
        ):
            existing_member_sets.setdefault(row['trend_id'], set()).add(f"{row['obj_type']}:{row['obj_id']}")
    
        matched_cluster_ids: set[int] = set()
        new_trends = 0
        updated_trends = 0
    
        util.ensure_views(conn)
        processed_clusters = 0
    
        for i, cluster_row in enumerate(clusters):
            trend_id = cluster_row['trend_id']
            if progress_cb:
                progress_cb(f"Processing cluster {i+1}/{len(clusters)}...")
            if util.is_cancelled():
                raise util.CancelledError('Cancelled during trend synthesis')
            
            # Get cluster members
            members = conn.execute("SELECT obj_id FROM trend_cluster_members WHERE trend_id = ?", (trend_id,)).fetchall()
            member_ids = [m['obj_id'] for m in members]
            cluster_items = [item for item in items if item['obj_id'] in member_ids]
            if len(cluster_items) < 2:
                continue
    
            member_keys = {f"story:{item['obj_id']}" for item in cluster_items}
            keywords, label, sample_titles = _top_terms_for_cluster(cluster_items, items, term_map)
            fingerprint = _fingerprint(keywords, [item['obj_id'] for item in cluster_items])
    
            llm_label = None
            llm_summary = None
            if use_llm_labels:
                llm_label, llm_summary = self._get_llm_label_for_cluster(cluster_items)
                if llm_label:
                    label = llm_label # Use LLM label if available
    
    
            signal_total = 0.0
            comment_total = 0.0
            sentiment_total = 0.0
            timestamps: list[int] = []
            for idx in cluster.members:
                item = items[idx]
                weight = _signal_weight(now, item['ts_unix'], window_days)
                base_signal = item['score'] + 0.6 * item['comments'] + 1.0 + item['sentiment'] * 0.5
                signal_total += base_signal * weight
                comment_total += item['comments']
                sentiment_total += item['sentiment']
                timestamps.append(item['ts_unix'])
    
            if not timestamps:
                continue
    
            average_sentiment = sentiment_total / len(cluster.members) if cluster.members else 0.0
    
            window_start = datetime.fromtimestamp(min(timestamps), tz=timezone.utc).date().isoformat()
            window_end = datetime.fromtimestamp(max(timestamps), tz=timezone.utc).date().isoformat()
            story_count = len(cluster.members)
    
            matched_row = existing_by_fp.get(fingerprint)
            trend_id: int | None = None
    
            if matched_row:
                trend_id = matched_row['trend_id']
            else:
                best_trend_id = None
                best_overlap = 0.0
                for candidate_id, existing_keys in existing_member_sets.items():
                    overlap = len(member_keys & existing_keys)
                    if not overlap:
                        continue
                    union = len(member_keys | existing_keys)
                    jaccard = overlap / union if union else 0.0
                    if jaccard > best_overlap and jaccard >= 0.35:
                        best_overlap = jaccard
                        best_trend_id = candidate_id
                if best_trend_id is not None:
                    trend_id = best_trend_id
    
            centroid_blob = cluster.centroid.astype(np.float32).tobytes()
            canonical_terms = ','.join(keywords)
            signal_delta = signal_total
            novelty = 1.0
            persistence = min(1.0, 1.0 / window_weeks)
            times_seen = 1
    
            if trend_id is None:
                new_trends += 1
                with conn:
                    cur = conn.execute(
                        """
                        INSERT INTO trend_clusters (
                            fingerprint,
                            canonical_label,
                            llm_summary,
                            canonical_terms,
                            first_seen,
                            last_seen,
                            times_seen,
                            latest_signal,
                            latest_delta,
                            latest_story_count,
                            latest_comment_count,
                            latest_sentiment,
                            novelty,
                            persistence,
                            centroid,
                            active
                        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            fingerprint,
                            label,
                            llm_summary,
                            canonical_terms,
                            today,
                            today,
                            signal_total,
                            signal_delta,
                            story_count,
                            int(comment_total),
                            average_sentiment,
                            novelty,
                            persistence,
                            centroid_blob,
                        ),
                    )
                    trend_id = int(cur.lastrowid)
                cluster_meta[trend_id] = {
                    'trend_id': trend_id,
                    'fingerprint': fingerprint,
                    'canonical_label': label,
                    'llm_summary': llm_summary,
                    'canonical_terms': canonical_terms,
                    'first_seen': today,
                    'last_seen': today,
                    'times_seen': 1,
                    'latest_signal': signal_total,
                    'latest_delta': signal_delta,
                    'latest_story_count': story_count,
                    'latest_comment_count': int(comment_total),
                    'latest_sentiment': average_sentiment,
                    'novelty': novelty,
                    'persistence': persistence,
                    'centroid': centroid_blob,
                    'active': 1,
                }
                existing_by_fp[fingerprint] = cluster_meta[trend_id]
            else:
                processed_clusters += 1
                matched_cluster_ids.add(trend_id)
                meta = cluster_meta.get(trend_id, {})
                previous_signal = float(meta.get('latest_signal') or 0.0)
                times_seen = int(meta.get('times_seen') or 0) + 1
                novelty = max(0.2, 1.0 / times_seen)
                persistence = min(1.0, times_seen / window_weeks)
                signal_delta = signal_total - previous_signal
                signal_total += (average_sentiment - previous_sentiment) * sentiment_weight
                with conn:
                    conn.execute(
                        """
                        UPDATE trend_clusters
                        SET fingerprint = ?,
                            canonical_label = ?,
                            llm_summary = ?,
                            canonical_terms = ?,
                            last_seen = ?,
                            times_seen = ?,
                            latest_signal = ?,
                            latest_delta = ?,
                            latest_story_count = ?,
                            latest_comment_count = ?,
                            latest_sentiment = ?,
                            novelty = ?,
                            persistence = ?,
                            centroid = ?,
                            active = 1
                        WHERE trend_id = ?
                        """,
                        (
                            fingerprint,
                            label,
                            llm_summary,
                            canonical_terms,
                            today,
                            times_seen,
                            signal_total,
                            signal_delta,
                            story_count,
                            int(comment_total),
                            average_sentiment,
                            novelty,
                            persistence,
                            centroid_blob,
                            trend_id,
                        ),
                    )
                meta.update(
                    fingerprint=fingerprint,
                    canonical_label=label,
                    llm_summary=llm_summary,
                    canonical_terms=canonical_terms,
                    last_seen=today,
                    times_seen=times_seen,
                    latest_signal=signal_total,
                    latest_delta=signal_delta,
                    latest_story_count=story_count,
                    latest_comment_count=int(comment_total),
                    latest_sentiment=average_sentiment,
                    novelty=novelty,
                    persistence=persistence,
                    centroid=centroid_blob,
                    active=1,
                )
                existing_by_fp[fingerprint] = meta
                cluster_meta[trend_id] = meta
                updated_trends += 1
    
            _ensure_cluster_members_table(conn, trend_id, member_keys, today)
    
            with conn:
                conn.execute(
                    """
                    INSERT INTO trend_snapshots (
                        trend_id, run_id, window_start, window_end, story_count, comment_count, signal, delta, novelty, persistence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trend_id,
                        run_id,
                        window_start,
                        window_end,
                        story_count,
                        int(comment_total),
                        signal_total,
                        signal_delta,
                        novelty,
                        persistence,
                    ),
                )
    
            matched_cluster_ids.add(trend_id)
    
        stale_ids = set(cluster_meta.keys()) - matched_cluster_ids
        if stale_ids:
            updates = []
            for trend_id in stale_ids:
                meta = cluster_meta.get(trend_id, {})
                previous_signal = float(meta.get('latest_signal') or 0.0)
                decayed_signal = previous_signal * stale_decay_factor
                updates.append((decayed_signal, trend_id))
    
            with conn:
                conn.executemany(
                    "UPDATE trend_clusters SET active = 0, latest_signal = ? WHERE trend_id = ?",
                    updates,
                )
    
        _calculate_term_surges(conn, run_id, cutoff_unix, window_days, progress_cb=progress_cb)
    
        _store_trend_history(conn, run_id)
    
        return {
            'trends': processed_clusters,
            'new_trends': new_trends,
            'updated_trends': updated_trends,
        }
