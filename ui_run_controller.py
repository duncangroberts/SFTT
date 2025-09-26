import json
import os
from datetime import datetime
import pandas as pd
from typing import Callable, Optional

import gdelt_fetch
import hn_fetch
import ingest
import db

def _default_config() -> dict:
    return {
        "timezone": "Europe/London",
        "weights": {
            "base_g": 0.7,
            "base_h": 0.3,
            "k_shrink": 200,
            "k_weight": 200,
        },
        "technologies": [
            {"id": "genai", "name": "Generative AI", "patterns": ["generative ai", "openai", "chatgpt"]}
        ]
    }

def load_config() -> dict:
    """Loads configuration from config.json; creates defaults if missing or corrupt."""
    path = 'config.json'
    if not os.path.exists(path):
        cfg = _default_config()
        save_config(cfg)
        return cfg
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            # Ensure weights defaults exist
            if 'weights' not in cfg or not isinstance(cfg.get('weights'), dict):
                cfg['weights'] = _default_config()['weights']
                save_config(cfg)
            else:
                # Fill any missing keys
                for k, v in _default_config()['weights'].items():
                    if k not in cfg['weights']:
                        cfg['weights'][k] = v
                        save_config(cfg)
            return cfg
    except Exception:
        cfg = _default_config()
        save_config(cfg)
        return cfg

def save_config(cfg: dict) -> None:
    """Persists configuration to config.json."""
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def run_month_update(target_month: str, logger: Optional[Callable[[str], None]] = None):
    """Fetch timelinetone, compute average_tone, attach Hacker News sentiment metrics, and persist raw monthly fields."""
    def log(msg: str):
        (logger or print)(msg)

    config = load_config()
    month_start_dt = datetime.strptime(target_month, "%Y-%m")
    # End of month at 23:59:59 UTC-equivalent boundary
    last_day = (month_start_dt + pd.DateOffset(months=1)) - pd.DateOffset(days=1)
    month_end_dt = last_day.replace(hour=23, minute=59, second=59)

    rows = []
    for tech in config['technologies']:
        log(f"Processing {tech['name']} for {target_month}")
        patterns = [p for p in (tech.get('patterns') or []) if p and str(p).strip()]
        if not patterns:
            patterns = [tech['name']]
        per_term_avgs: list[float] = []
        for p in patterns:
            q = gdelt_fetch.build_query([p], [])
            term_tones: list[float] = []
            for tp in gdelt_fetch.iter_timelinetone(tech['id'], q, month_start_dt, month_end_dt, logger=log):
                if tp.get('tone') is not None:
                    try:
                        term_tones.append(float(tp['tone']))
                    except Exception:
                        continue
            if term_tones:
                avg_p = sum(term_tones) / len(term_tones)
                per_term_avgs.append(avg_p)
                log(f"GDELT: term '{p}' tones={len(term_tones)} avg={avg_p:.3f}")
            else:
                log(f"GDELT: term '{p}' tones=0 avg=N/A")
        # Equal-weight average across subterms by feeding per-term averages into aggregator
        tone_records = [{"tone": t} for t in per_term_avgs]
        aggregated = ingest.aggregate_month(tech['id'], tech['name'], target_month, tone_records)
        log(f"GDELT(eq-term): average_tone={aggregated.get('average_tone')}")

        # Compute Hacker News score for the month
        try:
            hn_score, hn_count, hn_avg_comp = hn_fetch.compute_month_score(tech.get('patterns', []), month_start_dt, month_end_dt, logger=logger)
        except Exception as e:
            log(f"HN: error computing score for {tech['id']}: {e}")
            hn_score, hn_count, hn_avg_comp = (None, 0, None)

        # Store raw-only HN fields
        aggregated['hn_avg_compound'] = hn_avg_comp
        aggregated['hn_comment_count'] = hn_count

        rows.append(aggregated)

    # No normalization/combinations in raw-only model

    for r in rows:
        db.upsert_monthly_sentiment(r)
        log(f"Upserted: {r['tech_name']} {target_month} (avg_tone={r.get('average_tone')}, hn_avg={r.get('hn_avg_compound')}, n={r.get('hn_comment_count')})")

def run_monthly_update(logger: Optional[Callable[[str], None]] = None):
    """Runs the update for the last month for all technologies."""
    today = datetime.today()
    first_day_of_current_month = today.replace(day=1)
    last_day_of_last_month = first_day_of_current_month - pd.DateOffset(days=1)
    target_month = last_day_of_last_month.strftime("%Y-%m")
    run_month_update(target_month, logger=logger)

def run_initial_load(logger: Optional[Callable[[str], None]] = None):
    """Runs the initial 3-year data load."""
    today = datetime.today()
    for i in range(36):
        month_date = today - pd.DateOffset(months=i)
        target_month = month_date.strftime("%Y-%m")
        run_month_update(target_month, logger=logger)

def run_one_day(target_day: str, upsert: bool = False, logger: Optional[Callable[[str], None]] = None) -> list[dict]:
    """Runs the fetch pipeline for a single day across all technologies.

    - target_day: 'YYYY-MM-DD' UTC day boundary.
    - If upsert=True, aggregates the day's data into its month and upserts that
      single-day aggregation (useful for smoke tests; not a full monthly result).
    - Returns list of per-tech aggregated dicts.
    """
    def log(msg: str):
        (logger or print)(msg)

    config = load_config()
    day_dt = datetime.strptime(target_day, "%Y-%m-%d")
    start_dt = day_dt.replace(hour=0, minute=0, second=0)
    end_dt = day_dt.replace(hour=23, minute=59, second=59)
    month_str = day_dt.strftime("%Y-%m")

    results = []
    rows = []
    for tech in config.get('technologies', []):
        log(f"Processing {tech['name']} for {target_day}")
        patterns = [p for p in (tech.get('patterns') or []) if p and str(p).strip()]
        if not patterns:
            patterns = [tech['name']]
        per_term_avgs: list[float] = []
        for p in patterns:
            q = gdelt_fetch.build_query([p], [])
            term_tones: list[float] = []
            for tp in gdelt_fetch.iter_timelinetone(tech['id'], q, start_dt, end_dt, logger=log):
                if tp.get('tone') is not None:
                    try:
                        term_tones.append(float(tp['tone']))
                    except Exception:
                        continue
            if term_tones:
                avg_p = sum(term_tones) / len(term_tones)
                per_term_avgs.append(avg_p)
                log(f"GDELT(day): term '{p}' tones={len(term_tones)} avg={avg_p:.3f}")
            else:
                log(f"GDELT(day): term '{p}' tones=0 avg=N/A")

        tone_records = [{"tone": t} for t in per_term_avgs]
        aggregated = ingest.aggregate_month(tech['id'], tech['name'], month_str, tone_records)
        log(f"GDELT(day, eq-term): average_tone={aggregated.get('average_tone')}")

        # Compute Hacker News raw score for the single-day window
        try:
            _, hn_count, hn_avg_comp = hn_fetch.compute_month_score(tech.get('patterns', []), start_dt, end_dt, logger=logger)
        except Exception as e:
            log(f"HN(day): error computing score for {tech['id']}: {e}")
            hn_count, hn_avg_comp = (0, None)

        aggregated['hn_avg_compound'] = hn_avg_comp
        aggregated['hn_comment_count'] = hn_count

        rows.append(aggregated)
        results.append(aggregated)

    # No normalization step in day mode either

    if upsert:
        for r in rows:
            db.upsert_monthly_sentiment(r)
            log(f"Upserted single-day aggregation for {r['tech_name']} into {month_str}")
    else:
        for r in rows:
            log(f"{r['tech_name']} {target_day}: avg_tone={r.get('average_tone')}, hn_avg={r.get('hn_avg_compound')}, n={r.get('hn_comment_count')}")

    return results
