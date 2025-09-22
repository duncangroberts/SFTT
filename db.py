import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Iterable
import pandas as pd

DATABASE_FILE = 'tracker_data.sqlite'

def create_database():
    """Creates or migrates the SQLite database schema for monthly_sentiment.

    Simplifies schema by removing article_count and storing only average_tone-based scores.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Minimal raw schema as requested
    desired_cols = [
        'tech_id', 'tech_name', 'month',
        'average_tone',
        'hn_avg_compound', 'hn_comment_count',
        'analyst_lit_score', 'analyst_whimsy_score',
        'run_at'
    ]

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_sentiment (
            tech_id TEXT,
            tech_name TEXT,
            month TEXT,
            average_tone REAL,
            hn_avg_compound REAL,
            hn_comment_count INTEGER,
            analyst_lit_score REAL,
            analyst_whimsy_score REAL,
            run_at TEXT,
            PRIMARY KEY (tech_id, month)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_mentions (
            term TEXT NOT NULL,
            run_timestamp TEXT NOT NULL,
            window_days INTEGER NOT NULL,
            mentions INTEGER NOT NULL,
            base_score REAL NOT NULL,
            title_mentions INTEGER NOT NULL,
            comment_mentions INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (term, run_timestamp)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyword_mentions_term ON keyword_mentions (term, run_timestamp)")

    # Check for legacy columns and migrate if needed
    cursor.execute("PRAGMA table_info(monthly_sentiment)")
    cols = [row[1] for row in cursor.fetchall()]
    if set(cols) != set(desired_cols):
        # Create a new table with desired schema and migrate data
        cursor.execute("DROP TABLE IF EXISTS monthly_sentiment_new")
        cursor.execute("""
            CREATE TABLE monthly_sentiment_new (
                tech_id TEXT,
                tech_name TEXT,
                month TEXT,
                average_tone REAL,
                hn_avg_compound REAL,
                hn_comment_count INTEGER,
                analyst_lit_score REAL,
                analyst_whimsy_score REAL,
                run_at TEXT,
                PRIMARY KEY (tech_id, month)
            )
        """)

        # Transform and copy from old table if it exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='monthly_sentiment'")
        if cursor.fetchone():
            # Fetch all old rows
            cursor.execute("PRAGMA table_info(monthly_sentiment)")
            old_cols = [row[1] for row in cursor.fetchall()]
            cursor.execute("SELECT * FROM monthly_sentiment")
            old_rows = cursor.fetchall()
            def tone_to_0_100(t):
                if t is None:
                    return 50.0
                try:
                    val = ((float(t) + 10.0) / 20.0) * 100.0
                    return max(0.0, min(100.0, val))
                except Exception:
                    return 50.0
            for r in old_rows:
                m = dict(zip(old_cols, r))
                lit = m.get('analyst_lit_score') if 'analyst_lit_score' in old_cols else None
                whim = m.get('analyst_whimsy_score') if 'analyst_whimsy_score' in old_cols else None
                avg_tone = m.get('average_tone') if 'average_tone' in old_cols else None
                hn_count = m.get('hn_comment_count') if 'hn_comment_count' in old_cols else 0
                try:
                    hn_count = int(hn_count or 0)
                except Exception:
                    hn_count = 0
                hn_avg_comp = m.get('hn_avg_compound') if 'hn_avg_compound' in old_cols else None
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO monthly_sentiment_new (
                        tech_id, tech_name, month,
                        average_tone, hn_avg_compound, hn_comment_count,
                        analyst_lit_score, analyst_whimsy_score,
                        run_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m.get('tech_id'), m.get('tech_name'), m.get('month'),
                        avg_tone, hn_avg_comp, hn_count,
                        lit, whim,
                        m.get('run_at')
                    )
                )
        cursor.execute("DROP TABLE IF EXISTS monthly_sentiment")
        cursor.execute("ALTER TABLE monthly_sentiment_new RENAME TO monthly_sentiment")

    conn.commit()
    conn.close()

def upsert_monthly_sentiment(row: dict) -> None:
    """Upserts a monthly sentiment record with raw-only fields."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        REPLACE INTO monthly_sentiment (
            tech_id, tech_name, month,
            average_tone,
            hn_avg_compound, hn_comment_count,
            analyst_lit_score, analyst_whimsy_score,
            run_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row['tech_id'], row['tech_name'], row['month'],
        row.get('average_tone'),
        row.get('hn_avg_compound'), row.get('hn_comment_count'),
        row.get('analyst_lit_score'), row.get('analyst_whimsy_score'),
        row['run_at']
    ))
    conn.commit()
    conn.close()

def get_scores_for_month(month: str) -> list[dict]:
    """Retrieves all sentiment scores for a given month."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monthly_sentiment WHERE month = ?", (month,))
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]

def get_scores_for_previous_month(month: str) -> list[dict]:
    """Retrieves all sentiment scores for the month prior to the given month."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    # Calculate previous month
    current_month_dt = datetime.strptime(month, "%Y-%m")
    previous_month_dt = current_month_dt - pd.DateOffset(months=1)
    previous_month_str = previous_month_dt.strftime("%Y-%m")

    cursor.execute("SELECT * FROM monthly_sentiment WHERE month = ?", (previous_month_str,))
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(columns, row)) for row in rows]

def get_analyst_scores(tech_id: str, month: str) -> tuple[float | None, float | None]:
    """Returns (lit, whim) 0..1 or (None, None) if row not present."""
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute("SELECT analyst_lit_score, analyst_whimsy_score FROM monthly_sentiment WHERE tech_id=? AND month=?", (tech_id, month))
    r = cur.fetchone()
    conn.close()
    if not r:
        return (None, None)
    return (r[0], r[1])

def deduplicate_monthly_sentiment():
    """Removes duplicate rows keeping the latest run_at per (tech_id, month)."""
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    # Create a temp table of latest run_at per key
    cur.execute("""
        CREATE TEMP TABLE IF NOT EXISTS latest AS
        SELECT tech_id, month, MAX(run_at) AS max_run
        FROM monthly_sentiment
        GROUP BY tech_id, month
    """)
    # Delete rows older than latest
    cur.execute("""
        DELETE FROM monthly_sentiment
        WHERE (tech_id, month, run_at) NOT IN (
            SELECT m.tech_id, m.month, m.run_at
            FROM monthly_sentiment m
            JOIN latest l ON l.tech_id = m.tech_id AND l.month = m.month AND l.max_run = m.run_at
        )
    """)
    conn.commit()
    conn.close()
def record_keyword_mentions(entries: Iterable[dict], run_timestamp: datetime | str, window_days: int) -> None:
    """Persist aggregated keyword statistics for discovery runs."""
    entries = list(entries)
    if not entries:
        return
    if isinstance(run_timestamp, datetime):
        if run_timestamp.tzinfo is None:
            run_dt = run_timestamp.replace(tzinfo=timezone.utc)
        else:
            run_dt = run_timestamp.astimezone(timezone.utc)
        run_ts = run_dt.isoformat()
    else:
        run_ts = str(run_timestamp)
    rows = []
    for entry in entries:
        term = entry.get('term')
        if not term:
            continue
        try:
            mentions = int(entry.get('mentions') or 0)
        except Exception:
            mentions = 0
        try:
            base_score = float(entry.get('base_score') or entry.get('score') or 0.0)
        except Exception:
            base_score = 0.0
        try:
            title_mentions = int(entry.get('title_mentions') or 0)
        except Exception:
            title_mentions = 0
        try:
            comment_mentions = int(entry.get('comment_mentions') or 0)
        except Exception:
            comment_mentions = 0
        rows.append((
            str(term),
            run_ts,
            int(window_days),
            mentions,
            base_score,
            title_mentions,
            comment_mentions,
        ))
    if not rows:
        return
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.executemany(
        """
        INSERT OR REPLACE INTO keyword_mentions (
            term, run_timestamp, window_days, mentions, base_score, title_mentions, comment_mentions
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def get_keyword_baseline(term: str, lookback_days: int, as_of: datetime | str | None = None) -> dict:
    """Return average mentions and score for a term within the lookback window."""
    if lookback_days <= 0:
        raise ValueError('lookback_days must be positive')
    if as_of is None:
        as_of_dt = datetime.now(timezone.utc)
    elif isinstance(as_of, datetime):
        as_of_dt = as_of.astimezone(timezone.utc) if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    else:
        try:
            as_of_dt = datetime.fromisoformat(str(as_of))
            if as_of_dt.tzinfo is None:
                as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)
            else:
                as_of_dt = as_of_dt.astimezone(timezone.utc)
        except Exception:
            as_of_dt = datetime.now(timezone.utc)
    cutoff = as_of_dt - timedelta(days=lookback_days)
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT AVG(mentions), AVG(base_score), COUNT(*)
        FROM keyword_mentions
        WHERE term = ?
          AND run_timestamp >= ?
        """,
        (term, cutoff.isoformat()),
    )
    row = cursor.fetchone()
    conn.close()
    avg_mentions = float(row[0]) if row and row[0] is not None else 0.0
    avg_score = float(row[1]) if row and row[1] is not None else 0.0
    samples = int(row[2]) if row and row[2] is not None else 0
    return {
        'avg_mentions': avg_mentions,
        'avg_score': avg_score,
        'samples': samples,
    }
