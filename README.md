# Emerging Technology Intelligence Dashboard

## Overview

This desktop application combines structured news signals from GDELT with community discussions from Hacker News to track emerging technology trends. A Tkinter GUI wraps two cooperating pipelines:

- **Technology Trends (GDELT)** generates monthly sentiment baselines per tracked technology and stores analyst adjustments.
- **Discover (Hacker News + LLM)** uses a local `llama.cpp` server to summarise high-signal stories into recurring themes and charts the resulting discussion.

The system ships with local models, SQLite databases, and export tooling so analysts can run everything offline.

## Feature Highlights

- Dual data pipelines that reconcile automated GDELT sentiment with Hacker News community signals.
- Integrated local LLM workflow (via `llama-server.exe`) for naming themes, merging similar discussions, and scoring sentiment.
- Rich Tkinter UI: scheduled/monthly runs, analyst score entry, quadrant visualisation, comment volume tracking, trajectory plots, and export buttons.
- Dedicated Discover notebook with live logs, theme browser, chart exports, and an LLM server control panel.
- All persistence handled by SQLite (`tracker_data.sqlite`, `discover/db/discover.sqlite`) with helper utilities for deduplication and purging.

## Quick Start

1. Install Python 3.11 or newer.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```
3. Ensure `models/` contains at least one `.gguf` model. Two examples are provided (`Meta-Llama-3.1-8B-Instruct-Q5_K_S.gguf`, `mistral-7b-instruct-v0.2.Q4_K_M.gguf`).
4. Launch `tools/llama.cpp/llama-server.exe` manually or let the Discover tab start it for you.
5. Run the GUI:
   ```bash
   python main.py
   ```
   On Windows you can double-click `run_app.cmd` or use `pythonw.exe main.py` to hide the console window.

### Local LLM configuration

- The Discover tab searches `models/` for `.gguf` files and runs `tools/llama.cpp/llama-server.exe -m <model> -c 4096`.
- Override server settings with environment variables (`LLAMA_SERVER_URL`, `LLM_SERVER_URL`, `LLM_MODEL`) if you host the server elsewhere.
- The system prompt used for theme synthesis lives in `prompts/discovery_system_prompt.txt`. Editing that file (or using the GUI prompt editor once exposed) customises the LLM behaviour.

## Architecture

```
GDELT API ---------> gdelt_fetch.py -> ingest.py -> db.py -> tracker_data.sqlite -> GUI (Technology Trends)
Hacker News API ---> discover/src/hn_fetcher.py -> content_processor.py -> analysis.py & scoring.py -> discover/src/db_manager.py -> discover/db/discover.sqlite -> Discover GUI
local llama.cpp server <-- llm_client.py --> analysis.py / Discover GUI
```

### Key modules

- `main.py` boots the Tkinter application.
- `gui.py` orchestrates notebooks, plots (matplotlib), logging, exports, and threading.
- `ui_run_controller.py` coordinates Tech Trends runs (initial load, monthly run, ad-hoc dates) using `gdelt_fetch.py`, `hn_fetch.py`, and `ingest.py`.
- `db.py` manages the `tracker_data.sqlite` schema plus helper routines for upserts, deduplication, and keyword baselines.
- `discover/src/*` implements the Discover pipeline (Hacker News ingestion, LLM decisions, embedding storage, charts, and DB access).
- `llm_client.py` + `llm_runtime.py` wrap llama.cpp HTTP endpoints and basic completion helpers.

## Technology Trends (GDELT) Pipeline

1. Configuration (`config.json`):
   - `weights`: governs how Hacker News sentiment is blended (currently unused after raw-only simplification).
   - `technologies`: each entry supplies `id`, `name`, and `patterns` (strings forwarded to GDELT and HN searches).
2. `ui_run_controller.run_month_update/monthly_update/initial_load` orchestrate data pulls.
3. `gdelt_fetch.py` queries the GDELT Doc 2.0 `timelinetone` endpoint for each pattern inside the month window.
4. `ingest.aggregate_month` averages tone values per technology and stamps `run_at` (no derived momentum/conviction fields are stored).
5. `hn_fetch.compute_month_score` collects Hacker News sentiment (`hn_avg_compound`) and comment counts.
6. `db.upsert_monthly_sentiment` writes everything into `tracker_data.sqlite::monthly_sentiment`.
7. Analysts can enter literature/whimsy adjustments (-1..1) through the GUI; they are stored directly in the same table.

### tracker_data.sqlite schema

- `monthly_sentiment(tech_id TEXT, tech_name TEXT, month TEXT, average_tone REAL, hn_avg_compound REAL, hn_comment_count INTEGER, analyst_lit_score REAL, analyst_whimsy_score REAL, run_at TEXT, PRIMARY KEY (tech_id, month))`.
- `keyword_mentions(term TEXT, run_timestamp TEXT, window_days INTEGER, mentions INTEGER, base_score REAL, title_mentions INTEGER, comment_mentions INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(term, run_timestamp))` for optional keyword discovery tooling.
- Use `db.deduplicate_monthly_sentiment()` (available via the Database tab) to keep the latest row per `(tech_id, month)` pair.

## Discover (Hacker News Theme) Pipeline

1. `discover/src/pipeline.py` drives the run. It is called from `DiscoverTab` when "Run Discovery Pipeline" is pressed.
2. `hn_fetcher.fetch_stories_for_past_days` pulls top stories (default 30 days, min score 100, min comments 50) using the official Firebase API in parallel.
3. For each new story:
   - `content_processor.fetch_and_extract_text` grabs and cleans the linked article.
   - Comments are collected and concatenated with the title and article excerpt.
4. `analysis.extract_theme_from_text` sends a constrained prompt to the local llama.cpp server to obtain a mid-level theme label.
5. `analysis.get_embedding` encodes the theme name using the local `sentence-transformers` model (`models/all-MiniLM-L6-v2`). The embedding is stored as a NumPy blob.
6. Existing themes (with embeddings) are compared using cosine similarity. Matches above `MIN_MERGE_SIMILARITY = 0.6` are merged; otherwise a new theme is created.
7. `analysis.get_llm_sentiment_score` requests a numeric sentiment value (-1..1) from the LLM over the concatenated comment text.
8. `scoring.calculate_discussion_score` computes `score + descendants*2` as a proxy for engagement; `scoring.determine_trend` labels sentiment change as `rising`, `falling`, or `stable`.
9. `db_manager.update_theme` increments discussion score, overwrites sentiment score and trend fields, and stores story links in `theme_stories`.

### discover/db/discover.sqlite schema

- `themes(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, discussion_score INTEGER, sentiment_score REAL, discussion_score_trend TEXT, sentiment_score_trend TEXT, embedding BLOB, created_at TIMESTAMP, updated_at TIMESTAMP)`.
- `stories(id INTEGER PRIMARY KEY, title TEXT, url TEXT, processed_at TIMESTAMP)` prevents duplicate processing.
- `theme_stories(theme_id INTEGER, story_id INTEGER, PRIMARY KEY(theme_id, story_id))` associates stories with exactly one theme. A unique index on `story_id` is applied during setup.
- `discover/src/db_manager.setup_database()` runs on every Discover launch to apply schema changes and add any missing columns, then cleans orphaned links.

### Discover configuration

- `discover/discover_config.json` contains tuning constants (`comment_weight`, similarity thresholds, decay factors). Load it if you extend scoring or merging logic.
- The system prompt template at `prompts/discovery_system_prompt.txt` is rendered with `{max_themes}` and saved through `discovery_llm.py` helpers.

## Shared Utilities and Tests

- `keyword_discovery.py` offers standalone helpers for surfacing trending keywords across public chatter (usable via `python -m unittest test_keyword_discovery.py`).
- `tech_glossary.json` biases the keyword pipeline toward relevant domain terms.
- `test_api.py` exercises the GDELT/Hacker News fetchers with lightweight smoke tests.

## User Interface Walkthrough

### Technology Trends notebook

- **Run**: Initial 36 month backfill, last-month rerun, custom month run, one-day smoke tests, and a `Purge DB` action (dangerous—clears `monthly_sentiment`). Progress bars and the log console keep the user informed.
- **Database**: Table view of `monthly_sentiment` with `Refresh` and `Deduplicate Rows` buttons.
- **Analyst Scores**: Month selector plus grid entry boxes for literature & whimsy adjustments (-1..1). `Save All` persists to `monthly_sentiment`.
- **Quadrant**: Plots Conviction (analyst scores) against Momentum (tone/normalised sentiment) for a selected month. Supports PNG/CSV/JSON exports and theming.
- **Configuration**: Editor for `config.json` technologies, including ID, display name, and search patterns.
- **Comment Volume**: Bar chart of Hacker News comment counts per technology for a selected month.
- **Trajectories**: Line chart of sentiment trajectories over the last *N* months (configurable window).
- **Trends**: Rolling z-score of average tone to visualise momentum changes. Each chart tab exposes PNG export helpers that honour the active dark/light theme.

### Discover notebook

- **Themes tab (DiscoverTab)**: Treeview of top themes with discussion score, sentiment, and trend labels. Selecting a theme reveals story titles, Hacker News links, and supporting signals. Buttons allow refreshing data or purging the Discover database. Logs stream underneath via the Run sub-tab.
- **Run Discovery tab**: Start/stop buttons for the pipeline, log export (`.txt`), and status messages. Runs require the LLM server to be active.
- **LLM Server tab**: Dropdown of `.gguf` models, `Start Server` / `Stop Server` controls, and live stdout mirroring for troubleshooting.
- **Charts tab (`discover/src/charts_gui.py`)**: Side-by-side bar charts for top themes by discussion score and sentiment with PNG export.

The application theme can be toggled between light/dark, and all text widgets honour the active palette (see `App._apply_theme`).

## Operations & Maintenance

- **Monthly cadence**: Use the Run tab's "Run Monthly Update" after month end, then review Analyst Scores and export reports.
- **Database hygiene**: `Purge DB` (Technology Trends tab) clears `monthly_sentiment`; the Discover tab has its own purge button for `discover.sqlite`. Back up the SQLite files before pruning in production.
- **Deduplication**: Run the Database tab's dedupe button if multiple runs wrote the same `(tech_id, month)` with different `run_at` stamps.
- **LLM prompt tweaks**: Modify `prompts/discovery_system_prompt.txt` and restart the Discover pipeline to adjust theme naming.

## Testing

Run the existing tests before shipping changes:

```bash
python -m unittest test_keyword_discovery.py
python -m unittest test_api.py
```

You can add targeted smoke tests under the same pattern.

## Repository layout (selected)

```
assets/                     Static assets and screenshots
config.json                 Technology tracking configuration
discover/db/discover.sqlite Discover module SQLite database
discover/src/               HN pipeline modules (GUI, pipeline, analysis, scoring, db_manager, etc.)
db.py                       tracker_data schema + helpers
gdelt_fetch.py              GDELT API client
hn_fetch.py                 Hacker News sentiment helpers
llm_client.py               llama.cpp HTTP client
gui.py                      Tkinter application
models/                     Local embedding + llama.cpp models
requirements.txt            Python dependency list
tracker_data.sqlite         Technology Trends SQLite database
tools/llama.cpp/            Bundled llama.cpp binaries
```

## Housekeeping

Redundant specification drafts, temporary README fragments, generated logs, and helper scripts have been removed (`Discover.txt`, `tmp_readme_*.txt`, `discover/themes.md`, `discover/themeupdate.txt`, `discover/logs.txt`, `temp_edit.py`). Compiled bytecode under `discover/src/__pycache__` is also deleted to keep the repository lean.
