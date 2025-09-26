import sqlite3
from datetime import datetime
import pandas as pd
import numpy as np

from db import DATABASE_FILE

def aggregate_month(tech_id: str, tech_name: str, month: str, tone_records: list[dict]) -> dict:
    """Aggregates monthly data using only tone points from timelinetone.

    - Ignores article counts and URLs.
    - Returns average_tone for later combination with other signals.
    """
    if not tone_records:
        return {
            "tech_id": tech_id,
            "tech_name": tech_name,
            "month": month,
            "average_tone": None,
            "run_at": datetime.now().isoformat()
        }

    df = pd.DataFrame(tone_records)
    tone_series = pd.to_numeric(df.get('tone'), errors='coerce') if 'tone' in df else None
    average_tone = None
    if tone_series is not None:
        mean_val = tone_series.mean()
        average_tone = None if pd.isna(mean_val) else float(mean_val)

    return {
        "tech_id": tech_id,
        "tech_name": tech_name,
        "month": month,
        "average_tone": average_tone,
        "run_at": datetime.now().isoformat()
    }

def purge_database():
    """Deletes all data from the monthly_sentiment table."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM monthly_sentiment")
    conn.commit()
    conn.close()
