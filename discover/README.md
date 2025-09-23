# Discover Module Documentation

This document provides an overview of the Discover module, its functionality, and its technical implementation.

## 1. High-Level Goal

The primary objective of the Discover module is to analyze Hacker News content to automatically identify, score, and track trending discussion themes over time. It aims to provide a high-level view of what the tech community is talking about, how much they are talking about it, and what the general sentiment is.

## 2. How it Works: The Data Pipeline

The discovery process is an automated pipeline that can be triggered from the user interface.

### Step 1: Fetching Stories
A user-triggered function fetches the top 500 stories from Hacker News. It then filters these stories to find those posted within the last 30 days that meet a minimum threshold for engagement (100+ upvotes and 50+ comments by default).

### Step 2: Processing Content
For each new, highly-engaged story, the system fetches two types of content:
1.  The full text content from the story's URL.
2.  The text from all the comments on the Hacker News discussion thread.

### Step 3: Analysis (Theme & Sentiment)
This is the core of the pipeline where the raw text is analyzed.

#### Theme Extraction & Generalization
The system uses a Large Language Model (LLM) to identify a "mid-level" theme from the combined text of the story and its comments. A sophisticated prompt guides the LLM to avoid themes that are too specific or too general.

Once a theme name is extracted, its vector embedding is generated using the `all-MiniLM-L6-v2` sentence transformer model.

#### Theme Merging
To avoid creating duplicate themes (e.g., "AI in Development" vs. "AI for Software Engineering"), the system compares the new theme's vector embedding to the embeddings of all existing themes in the database. 

- If the **cosine similarity** between the new theme and an existing theme is greater than a threshold of **0.9**, the themes are considered a match. The new story's scores are merged into the existing theme.
- If no match is found, a new theme is created.

#### Sentiment Analysis
To get a more nuanced sentiment score, the system uses an LLM. The text from the story's comments is sent to the LLM with a prompt that asks it to return a single floating-point number between -1.0 (very negative) and 1.0 (very positive).

### Step 4: Scoring & Storing
- **Discussion Score:** A score is calculated for the story based on its upvotes and comment count (`score + (comment_count * 2)`).
- **Database:** The theme, its scores, and trends are stored in a dedicated SQLite database. A link is also created in the `theme_stories` table to associate the processed story with its assigned theme.

## 3. Database Schema

The `discover.sqlite` database contains three tables:

- **`themes`**: Stores the unique themes and their aggregated scores.
  - `embedding`: A `BLOB` column that stores the theme's vector embedding as a numpy array.
- **`stories`**: Tracks stories that have already been processed to avoid duplication.
- **`theme_stories`**: An association table that creates a many-to-many relationship between themes and stories.

## 4. GUI Features

### Discover Tab
- **Run Discovery Pipeline:** A button to trigger the entire data pipeline.
- **Refresh Themes:** Updates the list of top themes from the database.
- **Purge Discover DB:** A button to safely delete all data from the `themes` and `stories` tables for clean testing runs.
- **Top Themes List:** A list showing the top 10 themes, their discussion and sentiment scores, and their trends.
- **Stories for Theme Panel:** When you click on a theme in the list, this panel appears at the bottom, showing the titles and URLs of all stories that have been assigned to that theme.

### LLM Server Controls
- **Model Selection Dropdown:** This dropdown menu is automatically populated with all `.gguf` model files found in the project's `/models` directory. 
- **Start/Stop Server:** Buttons to start and stop the local `llama-server.exe` process using the model selected in the dropdown.

### Discover Charts Tab
This tab provides visualizations of the discovered theme data, including bar charts for discussion and sentiment scores.

## 5. System Prompts

Below are the exact system prompts used to guide the LLM for theme extraction and sentiment analysis.

### Theme Extraction Prompt
```
You are an expert analyst. Your task is to identify a mid-level theme from the provided text. The theme should be a concise noun phrase that is not too general but not overly specific. For example:
- GOOD: 'AI-powered Code Generation', 'Advancements in Fusion Energy', 'The Rise of RISC-V Architecture'
- BAD (too general): 'Software Development', 'Energy'
- BAD (too specific): 'A company released a new library for sorting arrays'

Respond with only the theme name.
```

### Sentiment Analysis Prompt
```
You are a sentiment analysis expert. Analyze the sentiment of the provided text, which contains comments from a tech forum. Consider the overall tone, including nuance, sarcasm, and technical criticism. Respond with only a single floating-point number between -1.0 (very negative) and 1.0 (very positive).
```
