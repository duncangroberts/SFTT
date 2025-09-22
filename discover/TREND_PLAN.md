# Hacker News Trend Tracking Plan

## Goals
- Surface **emerging themes** on Hacker News instead of isolated stories.
- Keep the implementation lightweight but data-science informed.
- Persist enough history to see momentum, novelty, and hot terms run over run.

## Pipeline Overview
1. **Ingest** Hacker News stories + top comments.
2. **Clean & Embed** each story document (story text + comments) using a lightweight sentence-transformer (e.g., MiniLM) and cache the vectors.
3. **Semantic Binning**
   - Maintain a set of cluster centroids.
   - For each new story (sorted by recency), find nearest centroid via cosine similarity (>= 0.78).
   - Assign to the closest cluster or start a new cluster if no centroid is close.
   - Track per-cluster stats: member story IDs, accumulated score, comments, first/last seen timestamps.
4. **Labeling**
   - Compute TF-IDF over cluster documents and keep the top keywords.
   - Optionally call the local LLM (Mistral) to generate a 5-word label using the top titles.
5. **Signal Snapshot** (per run)
   - For every cluster, compute `signal = S (story_points + 0.6 * comments + 1) * decay(age)`.
   - Store a snapshot with signal, story count, comment count, novelty (1 / times_seen), persistence (times_seen / window_weeks).
   - Compute `momentum = signal_now - signal_prev` when previous snapshots exist.
6. **Hot Terms**
   - Keep a daily table of term scores (`term, day, score_sum`).
   - Flag terms whose current score is = 2× the 7-day moving average.
   - Link flagged terms back to clusters to show which themes align with the surge.

## UI Concepts
- **Top Themes Table**: columns `Theme`, `Stories`, `Signal`, `?`, `Novelty`.
- **Momentum Chart**: bar (or sparkline) for the highest-signal clusters.
- **Hot Terms Panel**: list terms with growth multiples and linked cluster labels.
- **Detail Pane**: for a selected theme, show member stories, top comments, and key terms.

## Data Footprint
- Reuse existing SQLite DB under `discover/db`.
- Tables to adjust/extend:
  - `embedding_meta`, `embeddings`, `terms` (already present).
  - `trend_clusters`, `trend_snapshots`, `trend_cluster_members` (with added columns for momentum metrics).
  - New helper tables/views (if needed) for daily term aggregates and hot-term flags.

## Implementation Steps
1. Refine `embed_index.py` to ensure comments are included and vectors cached.
2. Rebuild `microtrends.build_components()`
   - Maintain centroid list.
   - Assign stories to clusters with the NN strategy.
   - Update cluster metadata and generate snapshots.
3. Add term-surge computation (SQL view or materialised table) for hot terms.
4. Update `tk_discover.py`
   - Replace current trend table with the new theme/momentum layout.
   - Add hot-term panel and simplified chart.
5. (Optional) Integrate LLM labeling guarded behind a checkbox.

## Notes
- The approach keeps clustering logic transparent: cosine NN + TF-IDF for explainability.
- Signal and momentum are easy to interpret, making it clear why a theme is “hot”.
- The plan leaves room for future upgrades (graph clustering or sentiment) without overhauling the schema.
