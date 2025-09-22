# Discover Module

Focused pipeline for the Discover tab built around Hacker News. A single on-demand run pulls recent stories and comments, encodes them, then rolls them into trend clusters with a strength signal tracked over time. Everything stays isolated under `discover/` using the dedicated SQLite database at `discover/db/discover.sqlite`.

## Run the pipeline once

```
python discover/src/run_once.py --since 7d --embed-model C:/Users/dunca/Desktop/SFTT/models/all-MiniLM-L6-v2
```

Flags worth knowing:
- `--since Nd` — lookback window (default `7d`).
- `--embed-model <name|path>` — SentenceTransformer model to encode story text (set to `none` to skip embeddings and trend detection).
- `--llm-labels` — try to label trends with the local llama.cpp server instead of keyword heuristics.

## Layout

```
discover/
  README.md
  FEATURE_NOTES.md
  __init__.py
  db/
    discover.sqlite
  src/
    schema.sql         # schema + trend tables
    views.sql          # helper views for UI/analytics
    util.py            # shared helpers (DB, logging, cancellation)
    hn_fetch.py        # Hacker News ingestion
    embed_index.py     # story embeddings + term extraction
    microtrends.py     # trend clustering + signal scoring
    run_once.py        # CLI entry point
    tk_discover.py     # Tkinter tab for the Discover UI
```

## What the new tab shows

- A single chart that tracks signal strength for the strongest trends run-over-run.
- A compact table of current trends with their signal delta, story count, and novelty score.
- Detail panel listing the key Hacker News stories/comments contributing to the selected trend.
- Recent pipeline runs with status + summaries.

## Operational notes

- The pipeline is idempotent; reruns only touch fresh Hacker News items.
- Embedding metadata is cached so only new/changed stories are re-encoded.
- Trend history (`trend_clusters`, `trend_cluster_members`, `trend_snapshots`) persists, allowing the signal chart to show momentum across runs.
- Cancellation is cooperative at every stage (fetch, encode, trend build) so the Stop button reacts quickly.

## Embeddings & labels

Point the “Embedding model” field at a local SentenceTransformer folder (e.g. `models/all-MiniLM-L6-v2`). Install the `sentence_transformers` package in your environment before running.

Enable the “LLM labels” checkbox (or `--llm-labels`) to ask the local llama.cpp server for short trend titles; otherwise keyword heuristics name the clusters.
