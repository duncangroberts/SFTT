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
    """Creates the database and tables if they do not exist."""
    os.makedirs(DB_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, check_same_thread=False) as conn:
        with open(SCHEMA_PATH, 'r', encoding='utf-8') as schema_file:
            conn.executescript(schema_file.read())
        columns = {row[1] for row in conn.execute("PRAGMA table_info(themes)")}
        if columns and 'embedding' not in columns:
            print("Adding 'embedding' column to themes table.")
            conn.execute("ALTER TABLE themes ADD COLUMN embedding BLOB")
        cleanup_theme_story_links(connection=conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_theme_stories_story ON theme_stories(story_id)")
        conn.commit()

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

def get_theme_by_id(theme_id):
    """Gets a theme by its ID."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM themes WHERE id = ?", (theme_id,))
        theme = cursor.fetchone()
        return dict(theme) if theme else None

def get_all_themes_with_embeddings():
    """Retrieves all themes with their embeddings."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT id, name, embedding FROM themes")
        themes = cursor.fetchall()
        return [dict(theme) for theme in themes]

def link_story_to_theme(story_id, theme_id):
    """Associates a story with exactly one theme, replacing any previous link."""
    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM theme_stories WHERE story_id = ?",
            (story_id,)
        )
        conn.execute(
            "INSERT INTO theme_stories (story_id, theme_id) VALUES (?, ?)",
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



def get_story_titles_for_theme(theme_id, limit=3):
    """Returns up to limit story titles for the given theme, newest first."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """SELECT s.title
               FROM stories s
               JOIN theme_stories ts ON s.id = ts.story_id
               WHERE ts.theme_id = ?
               ORDER BY s.processed_at DESC
               LIMIT ?
            """,
            (theme_id, limit)
        )
        return [row['title'] for row in cursor.fetchall() if row['title']]



def cleanup_theme_story_links(connection=None):
    """Ensures each story maps to a single theme and removes orphaned links."""
    def _cleanup(conn):
        conn.execute(
            """DELETE FROM theme_stories
            WHERE story_id NOT IN (SELECT id FROM stories)
               OR theme_id NOT IN (SELECT id FROM themes)
            """
        )
        conn.execute(
            """DELETE FROM theme_stories
            WHERE rowid NOT IN (
                SELECT MAX(rowid)
                FROM theme_stories
                GROUP BY story_id
            )
            """
        )
        conn.commit()

    if connection is not None:
        _cleanup(connection)
    else:
        with get_db_connection() as conn:
            _cleanup(conn)


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
    """Deletes all discovery data, including theme/story associations."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM theme_stories")
        conn.execute("DELETE FROM themes")
        conn.execute("DELETE FROM stories")
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('themes', 'stories')")
        conn.commit()
        print("Discover database has been purged.")


if __name__ == '__main__':
    # This allows setting up the database by running the script directly
    print("Setting up the Discover database...")
    setup_database()
