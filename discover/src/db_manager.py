#!/usr/bin/env python
"""Manages the connection and queries to the SQLite database."""

import sqlite3
import os
import numpy as np
import io
from contextlib import contextmanager

# --- Numpy array adapter for sqlite ---
def adapt_array(arr):
    out = io.BytesIO()
    np.save(out, arr)
    out.seek(0)
    return sqlite3.Binary(out.read())

def convert_array(text):
    out = io.BytesIO(text)
    out.seek(0)
    return np.load(out)

# Converts np.array to TEXT when inserting
sqlite3.register_adapter(np.ndarray, adapt_array)

# Converts TEXT to np.array when selecting
sqlite3.register_converter("array", convert_array)

# Database path
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'db')
DB_PATH = os.path.join(DB_DIR, 'discover.sqlite')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')

def setup_database():
    """Creates the database and tables if they don't exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    # Use check_same_thread=False to allow access from different threads (GUI and pipeline)
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        # Check if embedding column exists
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT embedding FROM themes LIMIT 1")
        except sqlite3.OperationalError:
            print("Adding 'embedding' column to themes table.")
            cursor.execute("ALTER TABLE themes ADD COLUMN embedding BLOB")
            conn.commit()

        with open(SCHEMA_PATH, 'r') as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        print("Database setup complete.")

@contextmanager
def get_db_connection():
    """Provides a database connection."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def add_story(story_id, title, url):
    """Adds a new story to the stories table."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO stories (id, title, url) VALUES (?, ?, ?)",
            (story_id, title, url)
        )
        conn.commit()

def is_story_processed(story_id):
    """Checks if a story has already been processed."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT id FROM stories WHERE id = ?", (story_id,))
        return cursor.fetchone() is not None

def get_or_create_theme(theme_name, embedding):
    """Gets a theme by name, creating it if it doesn't exist."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM themes WHERE name = ?", (theme_name,))
        theme = cursor.fetchone()
        if theme is None:
            cursor = conn.execute(
                "INSERT INTO themes (name, embedding) VALUES (?, ?)",
                (theme_name, embedding)
            )
            conn.commit()
            cursor = conn.execute("SELECT * FROM themes WHERE name = ?", (theme_name,))
            theme = cursor.fetchone()
        return dict(theme) if theme else None

def get_theme_by_name(theme_name):
    """Gets a theme by its name."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM themes WHERE name = ?", (theme_name,))
        theme = cursor.fetchone()
        return dict(theme) if theme else None

def get_all_themes_with_embeddings():
    """Retrieves all themes with their embeddings."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT id, name, embedding FROM themes")
        themes = cursor.fetchall()
        return [dict(theme) for theme in themes]

def link_story_to_theme(story_id, theme_id):
    """Creates an association between a story and a theme."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO theme_stories (story_id, theme_id) VALUES (?, ?)",
            (story_id, theme_id)
        )
        conn.commit()

def get_stories_for_theme(theme_id):
    """Retrieves all stories associated with a given theme."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """SELECT s.title, s.url, s.id 
               FROM stories s
               JOIN theme_stories ts ON s.id = ts.story_id
               WHERE ts.theme_id = ?
            """,
            (theme_id,)
        )
        stories = cursor.fetchall()
        return [dict(story) for story in stories]



def update_theme(theme_id, discussion_score, sentiment_score, discussion_trend, sentiment_trend):
    """Updates a theme's scores and trends."""
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE themes
            SET
                discussion_score = discussion_score + ?,
                sentiment_score = ?,
                discussion_score_trend = ?,
                sentiment_score_trend = ?
            WHERE id = ?
            """,
            (discussion_score, sentiment_score, discussion_trend, sentiment_trend, theme_id)
        )
        conn.commit()

def get_top_themes(limit=10):
    """Retrieves the top themes based on discussion score."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM themes ORDER BY discussion_score DESC LIMIT ?",
            (limit,)
        )
        themes = cursor.fetchall()
        return [dict(theme) for theme in themes]

def purge_discover_database():
    """Deletes all data from the themes and stories tables."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM themes")
        conn.execute("DELETE FROM stories")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='themes'") # Reset autoincrement
        conn.commit()
        print("Discover database has been purged.")


if __name__ == '__main__':
    # This allows setting up the database by running the script directly
    print("Setting up the Discover database...")
    setup_database()