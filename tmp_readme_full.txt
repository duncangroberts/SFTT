# Emerging Technology Quadrant Generator

Local desktop app that tracks public sentiment for emerging technologies using the free GDELT Doc 2.0 API and renders a monthly Momentum vs Conviction quadrant. Data is stored in SQLite; analysts add subjective “Literature” and “Whimsy” scores in the UI.

This app now uses a simplified, fast pipeline: timelinetone-only (no artlist, no article counts).

## Quick Start
- Requirements: Python 3.11+, packages: `requests`, `pandas`, `numpy`, `matplotlib` (Tkinter ships with Python on Windows).
- Launch without a console: double‑click `run_app.cmd`.
  - Or run from a shell: `python main.py` (use `pythonw.exe` to hide the console).

## What It Does
- Fetches aggregate tone for configured technologies via GDELT `mode=timelinetone` (English sources only).
- Computes monthly metrics per technology:
  - `average_tone` (from timelinetone)
  - `sentiment_score` = `average_tone`
  - `momentum_score` = normalized sentiment (z‑score across techs for that month); persisted in DB
  - `conviction_score` = `analyst_lit_score + analyst_whimsy_score` (entered in UI; each score stored 0..1)
- Renders a Quadrant: X = Momentum (normalized), Y = Conviction.
- Exports Quadrant data to PNG/CSV/JSON.

## Architecture
- `main.py` — starts the Tkinter GUI.
- `gui.py` — all UI tabs and interactions (Run, Database, Analyst Scores, Quadrant, Configuration).
- `ui_run_controller.py` — orchestrates runs (selected month, last month, initial backfill, one‑day) and writes normalized momentum to DB.
- `gdelt_fetch.py` — GDELT client:
  - `build_query(patterns)` → `("a" OR "b") sourcelang:eng`
  - `iter_timelinetone(...)` → yields `{date, tone}` values for a date range
- `ingest.py` — aggregates tone to monthly `average_tone` and `sentiment_score`.
- `db.py` — SQLite schema creation/migration and upsert helpers.
- `config.json` — technologies (`id`, `name`, `patterns[]`) and UI defaults.
- `tracker_data.sqlite` — local SQLite database.

## Data Model
SQLite table `monthly_sentiment` (PK: `tech_id`, `month`):
- `tech_id` TEXT, `tech_name` TEXT, `month` TEXT (YYYY‑MM)
- `average_tone` REAL, `sentiment_score` REAL, `momentum_score` REAL
- `analyst_lit_score` REAL (0..1), `analyst_whimsy_score` REAL (0..1), `conviction_score` REAL
- `run_at` TEXT (ISO timestamp)

Notes
- Schema migrations run automatically at startup to remove older `article_count` columns.
- `momentum_score` is persisted as a z‑score across all techs for that month so the Quadrant is visually separated.

## How It Works
1) Build a query per technology combining sub‑terms with OR and restricting to English:
   - Example: `("generative ai" OR "openai" OR "chatgpt") sourcelang:eng`
2) Call `timelinetone` for the selected month; collect tone values.
3) Aggregate `average_tone`; set `sentiment_score = average_tone`.
4) Normalize momentum across all techs for the month: z‑score of `sentiment_score`; store in DB.
5) Analysts enter Literature/Whimsy (0–100) in the UI; values are stored normalized (0..1), and `conviction = lit + whimsy`.

## GUI Overview
Run
- Initial 3‑Year Data Load: sequentially runs the last 36 months.
- Run Last Month’s Update: recompute for last completed month.
- Run Selected Month (YYYY‑MM): type a month and run it exactly.
- Run Specific Day (YYYY‑MM‑DD): quick test; aggregates a single day’s tone into its month and persists normalized momentum when upserting.
- Purge Database: wipes `monthly_sentiment`.

Database
- Read‑only table of `monthly_sentiment`. Auto‑refreshes on startup and after runs/saves.

Analyst Scores
- Pick a month (editable). A grid shows every technology with two inputs:
  - Literature (0–100)
  - Whimsy (0–100)
- “Save All” writes all scores at once; creates rows if missing.
- Scores are stored normalized (0..1); `conviction_score = lit + whimsy`.

Quadrant
- Select month to render X = Momentum (normalized, from DB), Y = Conviction (derived from analyst scores).
- Exports: PNG (chart), CSV/JSON (tech_name, momentum_score, conviction_score for the month).

Configuration
- Manage Technologies: `id`, `name`, `patterns[]`.
- Save writes `config.json` and refreshes other views.

## Running the App
- Double‑click: `run_app.cmd` (uses `pythonw.exe` if available to hide the console).
- Create a desktop shortcut (optional):
  - Target: `"C:\\path\\to\\pythonw.exe" "C:\\Users\\<you>\\Desktop\\SFTT\\main.py"`
  - Start in: `C:\\Users\\<you>\\Desktop\\SFTT`
  - Change Icon… to set a custom icon.

## Example API Request
The app issues timelinetone requests similar to:
```
https://api.gdeltproject.org/api/v2/doc/doc?query=(%22generative%20ai%22%20OR%20%22openai%22%20OR%20%22chatgpt%22)%20sourcelang:eng&mode=timelinetone&startdatetime=20240801000000&enddatetime=20240831235959&format=json
```

## CLI Smoke Test (optional)
```
python test_api.py
```
- Prints average tone for a recent day using timelinetone only.

## Troubleshooting
- No months appear in Analyst Scores after a purge
  - Type a month (YYYY‑MM) and “Save All” to create rows; or Run Selected Month first.
- Quadrant has little/no X‑axis variation
  - Ensure multiple techs have been processed for that month; normalization is across techs for the month.
- Timelinetone returns no values
  - Try a different month or expand patterns; GDELT data coverage varies.
- GUI shows a console window on launch
  - Use `run_app.cmd` or target `pythonw.exe` in your shortcut.

## Files
- App core: `gui.py`, `ui_run_controller.py`, `gdelt_fetch.py`, `ingest.py`, `db.py`, `main.py`
- Config/DB: `config.json`, `tracker_data.sqlite`
- Launchers/Tests: `run_app.cmd`, `test_api.py`
- Docs: `README.md`, `spec.md`, `apichange.md`

## Change Log (recent)
- Simplified ingestion to timelinetone only; removed domain filters and article counts.
- Persist normalized momentum per month across techs.
- Analyst Scores grid for all techs at once; 0–100 inputs normalized to 0..1.
- Added “Run Selected Month (YYYY‑MM)” control.
- DB auto‑migrates schema and DB view auto‑refreshes on app start.

