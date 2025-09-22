# Emerging Technology Intelligence Dashboard

## Overview

This desktop application provides a comprehensive dashboard for tracking and analyzing emerging technology trends. It integrates data from various sources, including Hacker News and GDELT, to offer both quantitative metrics and qualitative insights into technology momentum, adoption, and sentiment. The application features a modular design with a Tkinter-based graphical user interface (GUI) for easy interaction and visualization.

### Key Features

*   **Multi-Source Data Ingestion**: Collects data from Hacker News stories and comments, and GDELT's global news monitoring.
*   **Advanced Trend Discovery**: Utilizes natural language processing (NLP) techniques, including sentence embeddings and clustering, to identify emerging themes rather than just isolated keywords.
*   **Quantifiable Trend Metrics**: Calculates "Signal," "Velocity," "Novelty," and "Persistence" scores for identified themes, enabling data-driven analysis.
*   **Real-time Logging**: Provides detailed, real-time feedback on pipeline execution within the GUI.
*   **Interactive Visualizations**: Offers various charts and tables, including a "Trend Quadrant" for high-level strategic insights and detailed views of individual themes.
*   **Extensible Architecture**: Designed to allow for easy integration of new data sources and analytical components.

## Core Concepts & Metrics

*   **Embeddings**: Numerical representations of text (stories, repo descriptions, READMEs) that capture semantic meaning. Used for finding similar content.
*   **Signal**: A primary metric for a trend's current importance, combining popularity (HN points) with a time-decay factor (newer content contributes more).
*   **Velocity**: (Previously "Momentum") Measures the change in a trend's Signal over time. A high positive Velocity indicates a rapidly growing trend.
*   **Novelty**: Indicates how new a trend is. High for newly identified themes, decreasing as a theme persists.
*   **Persistence**: Measures how consistently a trend appears over time. High for enduring themes.
*   **Clustering**: The process of grouping semantically similar stories into distinct themes.
*   **Hot Terms**: Individual keywords showing a significant surge in mentions or relevance within recent data.

## Architecture & Data Flow

The application follows a modular architecture, with distinct components for data ingestion, processing, analysis, and visualization.

```
+-------------------+       +-------------------+       +-------------------+
|   Data Sources    |       |   Data Fetchers   |       |   Data Storage    |
|-------------------|       |-------------------|       |-------------------|
| - Hacker News     |-----> | - hn_fetch.py     |-----> | - discover.sqlite |
| - GDELT           |-----> | - gdelt_fetch.py  |-----> | - tracker_data.sqlite |
+-------------------+       +-------------------+       +-------------------+
                                      |
                                      v
+-------------------+       +-------------------+       +-------------------+
| Data Processing   |       | Trend Analysis    |       |   UI & Reporting  |
|-------------------|       |-------------------|       |-------------------|
| - embed_index.py  |-----> | - microtrends.py  |-----> | - gui.py          |
|   (Embeddings,    |       |   (Clustering,    |       | - tk_discover.py  |
|   Keywords)       |       |   Signal Calc.)   |       | - quadrant_view.py|
+-------------------+       +-------------------+       +-------------------+
```

### Core Modules

*   `main.py`: The main entry point for launching the Tkinter GUI.
*   `gui.py`: Manages the overall Tkinter application, including tab creation, theme management, and inter-tab communication.
*   `ui_run_controller.py`: Orchestrates the GDELT data ingestion and processing pipeline.
*   `db.py`: Handles SQLite database schema creation, migrations, and general data access for the GDELT module.
*   `config.json`: Stores application configuration, including technology patterns for GDELT analysis.
*   `tracker_data.sqlite`: SQLite database for GDELT-related data (`monthly_sentiment`).

### Discovery Module (Hacker News)

This module is responsible for identifying emerging trends from unstructured text data.

*   `discover/src/hn_fetch.py`: Fetches Hacker News stories and their top comments. It incrementally fetches new data and has an increased limit (2000 stories) to ensure comprehensive coverage.
*   `discover/src/embed_index.py`:
    *   Processes text from Hacker News stories (title + comments).
    *   Generates sentence embeddings for each item.
    *   Extracts meaningful keywords, utilizing an expanded stopword list to filter out common, uninformative words.
*   `discover/src/microtrends.py`:
    *   The core of the trend analysis.
    *   Calculates a "Signal" score for each item (story) based on its popularity metrics (HN score) and age, applying a time decay.
    *   Selects the **top 500 items by Signal score** for clustering, ensuring the analysis focuses on the most impactful content.
    *   Groups similar items into "themes" using a greedy clustering algorithm.
    *   Calculates "Velocity," "Novelty," and "Persistence" for each theme.
    *   Identifies "Hot Terms" by tracking surges in keyword mentions.
*   `discover/src/tk_discover.py`: The Tkinter UI component for the Discovery module. It's split into two sub-tabs:
    *   **Dashboard**: Displays the top emerging themes, a bar chart of their signal strength, a table of themes with their metrics, a list of hot terms, and a detailed view of items within a selected theme.
    *   **Run & Log**: Contains controls for running the Discovery pipeline (lookback days, embedding model, LLM labels) and a real-time log display showing the progress of each stage.
*   `discover/src/views.sql`: Defines SQL views, including `v_items`, which unifies Hacker News stories into a single logical table for consistent processing by `microtrends.py`.
*   `discover/db/discover.sqlite`: The SQLite database specifically for the Discovery module's data (raw HN stories/comments, embeddings, terms, trend clusters, and snapshots).

## Setup & Installation

### Prerequisites

*   Python 3.11+
*   `pip` (Python package installer)

### Dependency Installation

Open your terminal or command prompt and navigate to the project's root directory. Then run:

```bash
pip install requests pandas numpy matplotlib scikit-learn sentence-transformers
```

### spaCy Setup

The Discovery module uses spaCy for natural language processing. Install it and download the small English model:

```bash
pip install spacy
python -m spacy download en_core_web_sm
```

**Important**: If you are using a Python virtual environment, ensure it is activated *before* running the `pip install` and `python -m spacy download` commands.

### Running the Application

*   **Without a console (Windows)**: Double-click `run_app.cmd` in the project root.
*   **From a shell**:
    ```bash
    python main.py
    ```
    (Use `pythonw.exe main.py` on Windows to hide the console window.)

## User Workflow & UI Guide

The application's GUI is organized into several tabs, each serving a specific purpose.

### Run Tab

This tab is primarily for managing the GDELT data pipeline.
*   **Initial 3-Year Data Load**: Fetches and processes GDELT data for the last 36 months.
*   **Run Last Month's Update**: Recomputes data for the last completed month.
*   **Run Selected Month (YYYY-MM)**: Allows you to specify and run data processing for a particular month.
*   **Run Specific Day (YYYY-MM-DD)**: For quick tests, aggregates a single day's tone into its month.
*   **Purge Database**: Deletes all GDELT-related data (`monthly_sentiment`) from `tracker_data.sqlite`.
*   **Progress Bar & Status**: Shows the current state of the GDELT pipeline.
*   **Log Text Area**: Displays detailed logs for the GDELT pipeline runs.

### Database Tab

Provides a read-only view of the `monthly_sentiment` table from `tracker_data.sqlite`.
*   **Refresh Button**: Updates the displayed data.
*   **Deduplicate Rows**: Cleans up duplicate entries in the `monthly_sentiment` table, keeping only the latest run for each tech/month.

### Analyst Scores Tab

Allows manual input of qualitative scores for technologies in the GDELT analysis.
*   **Month Selector**: Choose the month for which to enter scores.
*   **Technology Grid**: Displays a grid of technologies where you can input "Literature" and "Whimsy" scores (0-100). These are normalized to 0-1 internally.
*   **Save All Button**: Persists all entered scores to the database.

### Quadrant Tab

Visualizes GDELT-based technology trends using "Momentum" and "Conviction" scores.
*   **Month Selector**: Choose the month to visualize.
*   **Plot**: Displays a scatter plot with technologies positioned based on their calculated Momentum (from GDELT tone) and Conviction (from analyst scores).
*   **Export Buttons**: Allows exporting the chart as PNG, or the underlying data as CSV/JSON.

### Comment Volume Tab

Shows the distribution of Hacker News comment volume across technologies (GDELT-related).

### Trajectories Tab

Visualizes the historical movement of technologies on the Momentum vs. Conviction quadrant over a selected number of months (GDELT-related).

### Trends Tab

Displays line graphs of technology momentum over time (GDELT-related).

### Discover Tab

This is the core of the Hacker News trend analysis. It's split into two sub-tabs:

#### Dashboard (Discover Sub-tab)

*   **Top Emerging Themes Chart**: A horizontal bar chart visualizing the Signal strength of the top themes.
*   **Themes Table**: Displays a table of identified themes with columns for:
    *   **Theme**: The canonical label for the cluster.
    *   **Signal**: The calculated importance score.
    *   **? prev (Delta)**: The change in Signal from the previous run (Velocity).
    *   **Items**: Number of stories in the theme.
    *   **Interactions**: Total comments (for HN).
    *   **Novelty**: How new the theme is.
    *   **Persistence**: How consistently the theme appears.
*   **Hot Terms**: A list of individual keywords currently surging in popularity.
*   **Item Details Pane**: When you select a theme from the table, this pane displays the individual Hacker News stories that constitute that theme, along with their relevant metrics (e.g., HN score/comments) and age.

#### Run & Log (Discover Sub-tab)

*   **Lookback (days)**: Sets the historical window for fetching data (e.g., 7 days, 30 days).
*   **Embedding model**: Specifies the path or name of the sentence transformer model to use.
*   **LLM labels**: Checkbox to enable/disable using a local LLM for generating human-readable theme labels.
*   **Run Discover Button**: Initiates the trend analysis pipeline.
*   **Stop Button**: Attempts to cancel the current run.
*   **Purge DB Button**: Deletes all Discovery module data (`discover.sqlite`).
*   **Status Bar**: Shows a brief status of the current operation.
*   **Real-time Log**: A text area that displays detailed, real-time logs of the Discovery pipeline's execution, including fetching, embedding, and clustering stages.

### Trend Quadrant Tab (NEW)

This new tab provides a strategic visualization of the Discovery module's themes.
*   **Plot**: A scatter plot where each point represents a discovered theme.
    *   **X-Axis: Velocity (Signal Change)**: How fast the theme's signal is changing.
    *   **Y-Axis: Signal (Discussion Volume)**: The current overall importance of the theme.
*   **Quadrants**: The plot is divided into four quadrants, helping to categorize themes:
    *   **Leading (Top-Right)**: High Signal, High Velocity - Hot and growing.
    *   **Established (Top-Left)**: High Signal, Low Velocity - Popular but stable or declining.
    *   **Emerging (Bottom-Right)**: Low Signal, High Velocity - New and rapidly gaining traction.
    *   **Niche (Bottom-Left)**: Low Signal, Low Velocity - Specialized or dormant.
*   **Refresh Data Button**: Updates the plot with the latest trend data from the Discovery module.

### LLM Prompt Tab

Allows customization of the system prompt used by the local LLM for generating theme labels in the Discovery module.

### Configuration Tab

Manages the technologies tracked by the GDELT module, including their IDs, names, and search patterns.

## Troubleshooting

*   **"AttributeError: 'DiscoverUI' object has no attribute 'story_tree'"**: This indicates a mismatch in UI component names after refactoring. (This should be fixed by recent updates).
*   **Same themes appear repeatedly**:
    *   Ensure `hn_fetch.py`'s story ID limit is sufficiently high (e.g., 2000).
    *   Verify that `microtrends.py` is processing the top 500 items by signal, not just the newest.
    *   Confirm that `discover.sqlite` is being purged or updated correctly between runs if you expect entirely new results.
*   **Empty Item Details Pane**: Ensure `tk_discover.py`'s `_populate_trend_details` method correctly handles the 'story' object type.
*   **LLM not generating labels**: Check the LLM Prompt tab for errors, ensure your local LLM server is running and accessible, and verify the embedding model path.
*   **No months appear in Analyst Scores after a purge**: Type a month (YYYY-MM) and "Save All" to create rows, or run a selected month first.
*   **Quadrant has little/no X-axis variation**: Ensure multiple technologies have been processed for that month; normalization is across technologies for the month.
*   **Timelinetone returns no values**: Try a different month or expand patterns; GDELT data coverage varies.
*   **GUI shows a console window on launch**: Use `run_app.cmd` or target `pythonw.exe` in your shortcut.

## Development & Contribution Notes

*   **Code Style**: Adhere to PEP 8.
*   **Modularity**: Keep components loosely coupled.
*   **Testing**: Run `python -m unittest` for relevant test files (e.g., `test_keyword_discovery.py`).

## Change Log (Recent)

*   **2025-09-18**:
    *   **Improved Trend Relevance**:
        *   Modified `microtrends.py` to limit clustering to the **top 500 items by Signal score**, ensuring more focused and dynamic themes.
        *   Increased Hacker News story fetch limit in `hn_fetch.py` to 2000.
    *   **UI/UX Refinements**:
        *   Refactored the **Discover tab** into two sub-tabs: "Dashboard" (for visualizations and results) and "Run & Log" (for controls and real-time logging).
        *   Implemented **real-time logging** in the "Run & Log" tab for better pipeline visibility.
        *   Added a new **"Trend Quadrant" tab** for visualizing Discovery themes based on "Signal" vs. "Velocity."
    *   **Bug Fixes**:
        *   Resolved `SyntaxError` due to markdown in `tk_discover.py`.
        *   Corrected `AttributeError` related to `story_tree` vs. `item_tree` in `tk_discover.py`.
