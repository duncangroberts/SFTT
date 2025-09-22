# Discover Tab Notes

## Purpose
- Single-source pipeline focused on Hacker News stories and comments.
- Stores everything in `discover/db/discover.sqlite` so the Discover tab stays sandboxed.
- UI highlights emerging story clusters with a live signal chart and concise tables.

## Run Sequence
1. Ensure schema & helper views exist (`DiscoverUI._ensure_db_ready`).
2. Compute cutoff from lookback (`--since Nd`).
3. Fetch HN stories + top-level comments via Firebase API (cursors keep reruns incremental).
4. Encode story + comment text with the configured SentenceTransformer (skipped when `--embed-model none`).
5. Cluster embeddings, score trend signals, persist clusters/members/snapshots.
6. Refresh views and UI caches.

## Schema Highlights (`schema.sql`)
- `stories`, `comments` — raw Hacker News content.
- `embeddings`, `embedding_meta`, `terms` — cached vectors + lightweight keyword weights.
- `trend_clusters`, `trend_cluster_members`, `trend_snapshots` — persistent trend graph + signal history.
- `run_logs`, `run_stage_logs`, `source_state` — execution history, stage timing, incremental cursors.

## Views
- `v_items` — story metadata + metrics (score/comments) for embedding joins.
- `v_story_daily_signal` — per-story daily score/comment counts (for future analytics).
- `v_trend_snapshots`, `v_trend_signal_history` — convenience views powering the chart + tables.

## UI (`tk_discover.py`)
- Controls: lookback days, embedding model path/name, optional LLM label toggle, Run/Stop/Purge buttons.
- Chart: top trend signal strength over recent runs (line plot).
- Trend table: signal, delta vs. previous run, story/comment volume, novelty score.
- Detail panel: top contributing stories + summary for the selected trend.
- Run history: last 12 runs with status + summary text.

## CLI (`run_once.py`)
```
python discover/src/run_once.py --since 7d --embed-model C:/path/to/all-MiniLM-L6-v2 --llm-labels
```
- `--since Nd` — lookback window in days (default 7).
- `--embed-model <name|path>` — SentenceTransformer to load (set to `none` to skip embeddings/trends).
- `--llm-labels` — ask the local llama.cpp server for short trend labels.

## Signals & Scoring
- Signal strength = S[(story points + 0.6×comment_count + 1) × exp(-age / decay)].
- Novelty decays with repeated sightings; persistence increases as the trend sticks around.
- Comment and story counts per trend snapshot make it easy to spot noisy vs. meaningful clusters.

## Dependencies
- `requests`, `pandas`, `numpy`, `matplotlib`, `sentence_transformers` (required for embeddings).
- Optional: local llama.cpp server (`llm_runtime.py`) for human-friendly labels.

*Last updated: minimalist HN-only Discover revamp.*
