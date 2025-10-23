# Emerging Technology Intelligence Dashboard

## Overview

This project is a comprehensive intelligence dashboard designed to track and analyze emerging technology trends. It combines data from various sources, including news articles from GDELT and community discussions from Hacker News, to provide a multi-faceted view of the technology landscape. The system is composed of a Python-based backend for data ingestion and analysis, and a React-based web client for data visualization. A key feature of the system is its use of large language models (LLMs) to extract themes, score sentiment, and merge similar discussions, all of which can be run locally.

The application is designed to be run as a desktop application with a Tkinter GUI, which provides a rich interface for controlling the data pipelines, viewing results, and configuring the system.

## Features

*   **Dual Data Pipelines:** The system integrates two distinct data pipelines:
    *   **Technology Trends (GDELT):** This pipeline fetches news articles from the GDELT project, calculates monthly sentiment baselines for tracked technologies, and allows for analyst adjustments.
    *   **Discover (Hacker News + LLM):** This pipeline fetches top stories from Hacker News, uses a local LLM to summarize them into recurring themes, and charts the resulting discussion volume and sentiment.
*   **Local LLM Integration:** The system is designed to work with a local `llama.cpp` server, allowing for offline analysis and ensuring data privacy. The LLM is used for theme extraction, sentiment analysis, and merging similar discussions.
*   **Rich Tkinter GUI:** The desktop application provides a comprehensive user interface with the following features:
    *   Control over data ingestion pipelines (run, schedule, and configure).
    *   Analyst score entry for adjusting sentiment scores.
    *   Multiple data visualizations, including quadrant views, comment volume charts, trajectory plots, and trend charts.
    *   A dedicated "Discover" notebook with a theme browser, chart exports, and an LLM server control panel.
*   **Web Client:** A React-based web client provides a modern and interactive dashboard for visualizing the collected data. It connects to a Firebase Firestore database to display real-time data and now ships with a trajectory animation workspace for recording movement clips straight from the chart.
*   **Local Data Storage:** All data is stored locally in SQLite databases, making the system portable and self-contained.

## How It Works (Architecture)

The system is composed of several key components that work together to collect, analyze, and visualize technology trends.

```
GDELT API ---------> gdelt_fetch.py -> ingest.py -> db.py -> tracker_data.sqlite -> GUI (Technology Trends)
Hacker News API ---> discover/src/hn_fetcher.py -> content_processor.py -> analysis.py & scoring.py -> discover/src/db_manager.py -> discover/db/discover.sqlite -> Discover GUI
local llama.cpp server <-- llm_client.py --> analysis.py / Discover GUI
Firebase <---------- web_client
```

### Key Modules

*   **`main.py`:** The entry point for the Tkinter application.
*   **`gui.py`:** The core of the Tkinter GUI, orchestrating all the different views and user interactions.
*   **`ui_run_controller.py`:** Coordinates the execution of the data ingestion pipelines.
*   **`gdelt_fetch.py` & `hn_fetch.py`:** Modules responsible for fetching data from the GDELT and Hacker News APIs, respectively.
*   **`ingest.py`:** Aggregates the fetched data and prepares it for storage.
*   **`db.py` & `discover/src/db_manager.py`:** Modules for managing the SQLite databases.
*   **`llm_client.py` & `llm_runtime.py`:** A client for interacting with the local `llama.cpp` server.
*   **`discover/src/analysis.py`:** The core of the "Discover" pipeline, responsible for theme extraction, sentiment analysis, and merging.
*   **`web_client/`:** The React-based web client for data visualization, now including the Trajectory Animations tab and a shared axis-domain helper (`src/constants/trajectoryDomainConfig.json`) so every trajectory-style chart stays aligned.

## Installation and Setup

To get the system up and running, you will need to set up both the Python backend and the React web client.

### Python Backend

1.  **Prerequisites:**
    *   Python 3.11 or newer.
    *   The `pip` package manager.

2.  **Installation:**
    *   Clone the repository to your local machine.
    *   Install the required Python packages using `pip`:
        ```bash
        pip install -r requirements.txt
        ```
    *   Download the `en_core_web_sm` model for the `spacy` library:
        ```bash
        python -m spacy download en_core_web_sm
        ```

3.  **Configuration:**
    *   The main configuration for the backend is in the `config.json` file. Here you can define the technologies to track, the keywords to search for, and other parameters.
    *   The "Discover" pipeline has its own configuration file at `discover/discover_config.json`.

4.  **Local LLM Setup:**
    *   The system is designed to work with a local `llama.cpp` server. You will need to download and set up `llama.cpp` separately.
    *   Place your `.gguf` models in the `models/` directory.
    *   You can start the `llama-server.exe` manually, or let the "Discover" tab in the GUI start it for you.

### React Web Client

1.  **Prerequisites:**
    *   Node.js and `npm` (or `yarn`).

2.  **Installation:**
    *   Navigate to the `web_client` directory:
        ```bash
        cd web_client
        ```
    *   Install the required `npm` packages:
        ```bash
        npm install
        ```

3.  **Configuration:**
    *   The Firebase configuration is located in `web_client/src/firebase.js`. You will need to replace the placeholder configuration with your own Firebase project's configuration.
    *   Trajectory chart domains are stored in `web_client/src/constants/trajectoryDomainConfig.json`. This file keeps the momentum/conviction midlines and ranges consistent across the dashboard, quadrant plot, embeds, and the animation workspace. Adjust the numbers here if you want to widen the axes, then rebuild and redeploy.

#### Trajectory Animations and Motion Capture

*   The dashboard now includes a **Trajectory Animations** tab. It streams the same monthly sentiment data as the main chart but renders an SVG animation with play/pause controls, frame stepping, and export-friendly trails—ideal for podcasts or screen recordings.
*   The animation player uses the shared axis envelope described above, ensuring that quadrant membership stays comparable month-on-month when you capture new clips.

## Usage

### Python Backend

To run the Python backend and the Tkinter GUI, simply run the `main.py` script:

```bash
python main.py
```

On Windows, you can also double-click the `run_app.cmd` file to start the application.

The GUI provides a comprehensive interface for interacting with the system. You can run the data ingestion pipelines, view the collected data, and configure the application's settings.

### React Web Client

To run the React web client, navigate to the `web_client` directory and run the following command:

```bash
npm start
```

This will start a local development server and open the web client in your default browser. The web client provides a dashboard for visualizing the data collected by the backend.

## Dependencies

### Python

The Python dependencies are listed in the `requirements.txt` file. The key dependencies include:

*   `requests`: For making HTTP requests to the GDELT and Hacker News APIs.
*   `pandas` & `numpy`: For data manipulation and analysis.
*   `matplotlib`: For creating plots and charts in the Tkinter GUI.
*   `scikit-learn`: For machine learning tasks, such as cosine similarity calculation.
*   `sentence-transformers`: For generating embeddings for themes.
*   `spacy` & `vaderSentiment`: For natural language processing and sentiment analysis.
*   `beautifulsoup4` & `lxml`: For parsing HTML and XML.
*   `google-cloud-firestore`: For interacting with the Firebase Firestore database.

### Web Client

The web client dependencies are listed in the `web_client/package.json` file. The key dependencies include:

*   `react` & `react-dom`: For building the user interface.
*   `react-router-dom`: For routing within the application.
*   `recharts`: For creating charts and visualizations.
*   `firebase`: For interacting with the Firebase Firestore database.
