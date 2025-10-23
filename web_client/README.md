# SFTT Technology Intelligence Platform

_Personal run-book and architecture notes for the Emerging Technology Intelligence stack._  
This repository bundles everything I need to collect, enrich, and present monthly technology intelligence: the desktop pipelines, the data stores, and the React/Firebase delivery layer (including the trajectory animation studio).

---

## 1. System Overview

| Layer | Purpose | Key Modules / Paths | Destination |
|-------|---------|---------------------|-------------|
| **Technology Tracker pipeline** | Pulls monthly tone for curated technologies from GDELT "timelinetone", blends with Hacker News sentiment and analyst adjustments. | `gdelt_fetch.py`, `ingest.py`, `db.py`, `config.json` | `tracker_data.sqlite` → Firestore `monthly_sentiment` |
| **Keyword & Theme Discovery** | Tracks Hacker News stories, clusters with LLM, records recurring themes and keyword baselines. | `hn_fetch.py`, `keyword_discovery.py`, `discover/` package, local `llama.cpp` via `llm_client.py` | `discover/db/discover.sqlite` → Firestore (`themes`, `stories`, `theme_stories`, `keyword_mentions`) |
| **Desktop Control Surface** | Tkinter UI for running pipelines, reviewing data, editing analyst scores, and pushing Firestore updates. | `gui.py`, `ui_run_controller.py`, `firestore_sync_gui.py`, `main.py` | Operator console |
| **Web Client (React)** | Public/embedded dashboard and animation workspace. | `web_client/src` (tabs under `components/`, animation in `components/animations/`) | Firebase Hosting |
| **Shared Configuration** | Keeps analyst-facing settings together. | `config.json`, `discover/discover_config.json`, `web_client/src/constants/trajectoryDomainConfig.json` | Referenced by pipelines and UI |

Data moves left-to-right: pipelines populate SQLite, the desktop UI adjusts/validates, the Firestore sync tab publishes, and the hosted React app (plus embeddable views) consumes the Firestore collections.

---

## 2. Pipelines & Data Flow

### 2.1 Technology Tracker (GDELT + HN + Analyst)
1. **Configuration** – `config.json`
   * `technologies`: id, display name, and GDELT query patterns.
   * `sources`: domains whitelisted for tone analysis.
   * `weights`: future-proof weighting parameters (stored with the run metadata).
2. **Fetch tone** – `gdelt_fetch.py`
   * Builds compliant GDELT queries (quotes multi-word terms, chunks long lists).
   * Calls `mode=timelinetone` per technology to retrieve monthly tone series.
   * Handles retries, malformed responses, and pagination limits.
3. **Combine sentiment** – `ingest.py`
   * Normalises tone values, merges with Hacker News aggregates (`hn_avg_compound`, `hn_comment_count`), and attaches analyst overrides (`analyst_lit_score`, `analyst_whimsy_score`).
4. **Persist** – `db.py`
   * `create_database()` migrates schema on launch.
   * `upsert_monthly_sentiment()` stores one row per (tech_id, month), deduping old runs.
5. **Review & adjust** – Desktop GUI (Technology Trends tab) exposes sliders/forms so I can tweak analyst scores. Everything stays local until I sync to Firestore.

### 2.2 Keyword & Theme Discovery (Hacker News + LLM)
1. **Fetch stories** – `discover/src/hn_fetcher.py` (invoked via `keyword_discovery.py`) gathers HN stories/comments inside the configured window.
2. **Summarise & cluster** – `keyword_discovery.py` sends batches to the local `llama.cpp` server through `llm_client.py`; themes and sentiment are computed offline.
3. **Store** – SQLite at `discover/db/discover.sqlite` holds `themes`, `stories`, join tables, and keyword metrics. Schema tooling lives in `discover/src/db_manager.py`.
4. **Baseline keywords** – `db.record_keyword_mentions()` aggregates term frequency over time. `get_keyword_baseline()` exposes rolling averages for comparison in the Discover UI.

### 2.3 Firestore Publication
* **Service account** – keep `serviceAccountKey.json` in the repo root (git-ignored).
* **Launch** – within the Tkinter app the “Firestore Sync” tab (`firestore_sync_gui.FirestoreSyncTab`) pushes tables into matching Firestore collections:
  * `tracker_data.sqlite` → `monthly_sentiment`
  * `discover/db/discover.sqlite` → `themes`, `stories`, `theme_stories`
  * keyword stats copied into `keyword_mentions`
* Sync currently rewrites every document (deterministic doc IDs). Future improvement: detect diffs before writing.

---

## 3. Desktop Application (Tkinter)

* **Entry point** – `python main.py` or double-click `run_app.cmd`. `create_database()` ensures schema migrations before UI boot.
* **Tabs**
  * **Technology Trends** – charts tone+sentiment; exposes analyst scoring controls.
  * **Discover** – notebook for HN themes, keyword spikes, and LLM server operations.
  * **Keyword Analytics** – leverages `keyword_mentions` for baselines/breakouts.
  * **Firestore Sync** – start long-running sync job and tail logs.
* **Background work** – `ui_run_controller.py` wraps long tasks in worker threads so the UI stays responsive.
* **Adding a new technology**
  1. Edit `config.json` with `id`, `name`, search `patterns`.
  2. Run the tracker pipeline for the desired history (via GUI).
  3. Adjust analyst scores if needed.
  4. Sync to Firestore so the web client and animations see the new series.

---

## 4. Web Client (React + Firebase)

### 4.1 Structure & Features
* **Auth** – anonymous sign-in triggered in `src/App.js`.
* **Routes**
  * `/` – dashboard tabs (Discover, Discover Charts, Technology Trends, Trajectory Animations).
  * `/embed/discover-charts`, `/embed/trajectory` – embeddable views with minimal chrome.
* **Realtime data** – components subscribe to Firestore using `onSnapshot` (see `src/components/embed/` and `src/components/charts/`).
* **Trajectory domain config** – `src/constants/trajectoryDomainConfig.json`
  * Stores momentum/conviction centre, half-range, and padding.
  * `computeTrajectoryDomains()` keeps the dashboard chart, quadrant plot, embeds, and animation player aligned. If new values breach the stored envelope the helper expands symmetrically around the saved centre—no quadrant drift.
* **Trajectory Animations tab** – `src/components/TrajectoryAnimationsTab.js`
  * Sidebar lists technologies; main pane renders `TrajectoryAnimationPlayer` with play/pause, speed slider, per-segment stats, and a trail-only animation (no future path). Perfect for podcast screen recordings.
  * Pulls the same `monthly_sentiment` data as the main chart (`fixedMonths=3` default) so narratives stay in sync.

### 4.2 Commands
```bash
cd web_client
npm install        # once
npm start          # local dev server
npm run build      # production bundle in /build
```
Deploy the `/build` output via Firebase Hosting (`firebase deploy`). Updating `trajectoryDomainConfig.json` requires rebuilding so the new envelope gets bundled.

---

## 5. Operational Checklist

| Task | When | Notes |
|------|------|-------|
| **Run tracker pipeline** | Monthly or after editing `config.json`. | Kick off from the UI. Monitor terminal/log for GDELT quota issues. |
| **Run discovery pipeline** | Weekly cadence ideal. | Ensure `llama.cpp` server is available; GUI tab can start/stop it. |
| **Review analyst overrides** | Post-ingestion. | Adjust in the GUI; values persist in SQLite and flow to Firestore. |
| **Sync to Firestore** | After QA. | Requires `serviceAccountKey.json`. Sync tab logs completion/errors. |
| **Capture trajectory animations** | During monthly podcast prep. | Use animation tab, adjust speed and restart controls, screen-record output. |
| **Backup SQLite** | Before large refactors. | `tracker_data.sqlite`, `discover/db/discover.sqlite`. |
| **Update web deploy** | After data refresh and config changes. | `npm run build` → `firebase deploy`. |
| **Tune axis envelope** | Only when new data breaks bounds. | Edit `web_client/src/constants/trajectoryDomainConfig.json` (centre/halfRange/padding), rebuild, redeploy. |

---

## 6. Code Review Notes / Future Improvements

* **Pipeline resilience**
  * `gdelt_fetch.iter_timelinetone` has basic error handling; adding exponential backoff and structured logs would help spot API limit issues quickly.
  * Consider caching raw GDELT responses on disk for auditability.
* **Firestore sync**
  * Currently rewrites entire tables. Adding a diff step (compare hash/timestamps) would cut write volume and speed up sync.
  * Sync jobs run in a background thread but still use per-row writes; batching documents (500 at a time) could reduce latency.
* **Configuration management**
  * `config.json` technology ids power SQLite PKs, Firestore doc ids, and chart color hashing. Treat changes as migrations; use scripts to backfill if renaming.
  * Domain envelope now lives in the web client; consider mirroring to Firestore so tweaks can happen without redeploy.
* **Testing**
  * There are unit tests for keyword discovery. Add coverage for GDELT query building, ingestion math, and Firestore sync (maybe via sqlite in-memory fixtures).
  * Snapshot tests for the React trajectory components would flag regressions when adjusting animation logic.
* **Security & access**
  * Service account JSON stays local. If sharing the repo, strip the file and rely on environment variables or secret manager.
  * Anonymous auth is fine for now; if exposing more broadly, enforce read-only Firestore rules and map embeds to custom claims.
* **Performance**
  * Animation UI uses `requestAnimationFrame`; for longer histories (>6 months) consider sampling points or adding a “frame skip” option.
  * SQLite dedup queries (`deduplicate_monthly_sentiment`) could benefit from indexed run timestamps. Current volumes are small enough that this isn’t urgent.

---

## 7. Quick Reference

* **Launch desktop UI**
  ```bash
  python main.py
  ```
* **Run tracker ingestion headless**
  ```bash
  python ingest.py --months 6   # example; check file for actual CLI usage
  ```
* **Start web client locally**
  ```bash
  cd web_client
  npm start
  ```
* **Sync to Firestore** – open desktop UI → Firestore Sync tab → “Sync to Firestore”.
* **Add a new technology**
  1. Update `config.json` with id/name/patterns.
  2. Re-run tracker pipeline for recent months.
  3. Adjust analyst scores as needed.
  4. Sync to Firestore, rebuild web client if domain envelope adjustments are required.

---

_Last updated: 23 Oct 2025_
