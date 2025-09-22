import json
from datetime import datetime, timedelta, timezone
from gdelt_fetch import build_query, iter_timelinetone

if __name__ == "__main__":
    # Load config for patterns
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception:
        cfg = {"technologies": [{"patterns": ["generative ai", "openai", "chatgpt"]}]}

    patterns = cfg.get('technologies', [{}])[0].get('patterns', ["ai", "openai", "chatgpt"])  # use first tech's patterns
    query = build_query(patterns, [])

    # Single day window a few days ago
    day = datetime.now(timezone.utc) - timedelta(days=3)
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59)

    tones = []
    for tp in iter_timelinetone('test', query, start, end):
        if 'tone' in tp and tp['tone'] is not None:
            tones.append(tp['tone'])

    if tones:
        avg_tone = sum(tones) / len(tones)
        print(f"Average tone (timelinetone) for day: {avg_tone:.3f}")
    else:
        print("No timelinetone values returned. Try a different date/patterns.")
