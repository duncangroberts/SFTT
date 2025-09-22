import requests
import json
import time
from datetime import datetime, timedelta
from urllib.parse import quote
import csv
from io import StringIO
import random

BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; sentiment-app/1.0)"}
MAX_QUERY_LEN = 900  # conservative limit to avoid GDELT "too long" errors

def _quote_term(term: str) -> str:
    """Quote terms that contain spaces or non-alphanumeric chars (e.g., dashes).

    GDELT rejects bare tokens with dashes like gpt-4; must be quoted.
    """
    t = term.strip().strip('"')
    needs_quotes = any((c.isspace() or not c.isalnum()) for c in t)
    return f'"{t}"' if needs_quotes else t

def build_queries(patterns: list[str], sources: list[str], max_len: int = MAX_QUERY_LEN) -> list[str]:
    """Build one or more queries that include all patterns and sources.

    - Quotes multi-word and dashed patterns.
    - Chunks patterns and sources as needed so each query stays under `max_len`.
    - Never silently drops sources; instead splits them across multiple queries.
    """
    pat_terms = [_quote_term(p) for p in patterns if p and p.strip()]
    src_terms = [f"domain:{s.strip()}" for s in sources if s and s.strip()]

    def make_group(terms: list[str]) -> str:
        return "(" + " OR ".join(terms) + ")" if terms else ""

    # First, chunk patterns so that the pattern group alone is < max_len
    pat_groups: list[list[str]] = []
    curr: list[str] = []
    for t in pat_terms:
        test = curr + [t]
        if len(make_group(test)) <= max_len or not curr:
            curr = test
        else:
            pat_groups.append(curr)
            curr = [t]
    if curr:
        pat_groups.append(curr)

    queries: list[str] = []
    for pg in pat_groups:
        pg_str = make_group(pg)
        if not src_terms:
            queries.append(pg_str)
            continue
        # Now chunk sources for this pattern group
        curr_src: list[str] = []
        for s in src_terms:
            test_src = curr_src + [s]
            q = f"{pg_str} {make_group(test_src)}".strip()
            if len(q) <= max_len or not curr_src:
                curr_src = test_src
            else:
                # flush current src group
                queries.append(f"{pg_str} {make_group(curr_src)}".strip())
                curr_src = [s]
        if curr_src:
            queries.append(f"{pg_str} {make_group(curr_src)}".strip())
    return queries

def build_query(patterns: list[str], sources: list[str] | None = None) -> str:
    """Build a timelinetone query string.

    Rules (per GDELT):
    - Parentheses may only wrap OR groups. For a single term, do NOT wrap in ().
    - Multi-word or dashed terms are quoted.
    - Always append sourcelang:eng.
    """
    terms = [_quote_term(p) for p in patterns if p and p.strip()]
    if not terms:
        core = ""
    elif len(terms) == 1:
        core = terms[0]
    else:
        core = f"({' OR '.join(terms)})"
    lang = "sourcelang:eng"
    return (f"{core} {lang}" if core else lang).strip()

def iter_timelinetone(tech_id: str, query: str, start_dt: datetime, end_dt: datetime, logger=None):
    """Yields tone points from mode=timelinetone within the date range.

    Output rows: {"date": datetime, "tone": float}
    """
    start_datetime_str = start_dt.strftime("%Y%m%d%H%M%S")
    end_datetime_str = end_dt.strftime("%Y%m%d%H%M%S")

    params = {
        'query': query,
        'mode': 'timelinetone',
        'format': 'JSON',
        'startdatetime': start_datetime_str,
        'enddatetime': end_datetime_str,
    }

    try:
        # Log the fully prepared URL for visibility/debugging
        try:
            preq = requests.Request('GET', BASE_URL, params=params).prepare()
            if logger:
                logger(f"GDELT GET {preq.url}")
        except Exception:
            pass
        response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=20)
        response.raise_for_status()
        text = response.text.strip()
        if not text or text.startswith('<'):
            print(f"timelinetone empty/HTML for {tech_id} {start_dt.strftime('%Y-%m')}")
            return
        try:
            data = response.json()
        except json.JSONDecodeError:
            print(f"timelinetone JSON decode failed for {tech_id}")
            return

        def collect_tones(obj, path, out):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    kl = str(k).lower()
                    new_path = path + [kl]
                    if isinstance(v, (int, float)):
                        if any(tok in kl for tok in ['tone', 'v2tone', 'avgtone', 'averagetone']):
                            out.append(float(v))
                        elif kl == 'value' and any('timeline' in p for p in new_path):
                            out.append(float(v))
                    elif isinstance(v, (dict, list)):
                        collect_tones(v, new_path, out)
            elif isinstance(obj, list):
                for item in obj:
                    collect_tones(item, path, out)

        tones = []
        collect_tones(data, [], tones)
        if not tones:
            # Try CSV fallback if JSON had no obvious tone values
            print(f"timelinetone JSON had no tone values for {tech_id}")
            return
        for t in tones:
            yield {"date": start_dt, "tone": t}
        print(f"timelinetone fetched {len(tones)} tone points for {tech_id} {start_dt.strftime('%Y-%m')}")
    except requests.exceptions.RequestException as e:
        print(f"timelinetone request failed for {tech_id}: {e}")

def iter_artlist_windows(tech_id: str, query: str, month_start: datetime, month_end: datetime):
    """Iterates daily 6-hour windows, performs GET with mode=artlist, and yields records."""
    current_day = month_start
    while current_day <= month_end:
        for hour_window in [(0, 6), (6, 12), (12, 18), (18, 24)]:
            start_hour, end_hour = hour_window
            window_start_dt = current_day.replace(hour=start_hour, minute=0, second=0)
            window_end_dt = current_day.replace(hour=end_hour - 1, minute=59, second=59)

            start_datetime_str = window_start_dt.strftime("%Y%m%d%H%M%S")
            end_datetime_str = window_end_dt.strftime("%Y%m%d%H%M%S")

            params = {
                'query': query,
                'mode': 'artlist',
                'format': 'CSV',
                'startdatetime': start_datetime_str,
                'enddatetime': end_datetime_str,
                'maxrecords': 250,
            }

            for i in range(3):
                try:
                    response = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
                    response.raise_for_status()
                    
                    text = response.text.strip()
                    # If response looks like HTML (error/ratelimit), treat as empty
                    if text.startswith('<'):
                        print(f"HTML-like response for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')}; treating as empty")
                        time.sleep(0.3 + random.random() * 0.2)
                        break
                    if not text:
                        print(f"Fetched 0 records for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')}")
                        time.sleep(0.3 + random.random() * 0.2)
                        break

                    # Parse CSV and yield records
                    csv_file = StringIO(text)
                    csv_reader = csv.reader(csv_file)
                    try:
                        header = next(csv_reader)  # Read header
                    except StopIteration:
                        print(f"Fetched 0 records for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')}")
                        time.sleep(0.3 + random.random() * 0.2)
                        break

                    # Find index of URL and Tone columns with flexible matching
                    raw_header = header[:]
                    # Trim BOM if present on first column name
                    raw_header[0] = raw_header[0].lstrip('\ufeff') if raw_header else ''
                    lower_header = [h.lower() for h in raw_header]

                    def find_idx(options: list[str]) -> int | None:
                        for opt in options:
                            if opt in lower_header:
                                return lower_header.index(opt)
                        return None

                    # If header clearly isn't normal CSV (error/no data), treat as empty
                    if len(raw_header) == 1 and any(k in lower_header[0] for k in ["no ", "error", "your search", "illegal"]):
                        print(f"Fetched 0 records for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')}")
                        time.sleep(0.3 + random.random() * 0.2)
                        break

                    url_idx = find_idx(['documentidentifier', 'url'])
                    tone_idx = find_idx(['v2tone', 'tone'])
                    date_idx = find_idx(['date', 'seendate'])

                    if url_idx is None:
                        print(f"Error: Missing URL column in GDELT response for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')}; header: {header}")
                        break  # Can't proceed without URL

                    yielded = 0
                    for row in csv_reader:
                        if len(row) <= url_idx:
                            continue
                        tone_value = None
                        if tone_idx is not None and len(row) > tone_idx:
                            try:
                                tone_value = float(row[tone_idx])
                            except ValueError:
                                tone_value = None
                        # Use provided Date if available; else window start
                        rec_date = window_start_dt
                        if date_idx is not None and len(row) > date_idx:
                            # Keep as window_start_dt for consistency; parsing string formats can vary
                            rec_date = window_start_dt

                        yield {
                            "date": rec_date,
                            "url": row[url_idx],
                            "tone": tone_value,
                        }
                        yielded += 1
                    print(f"Fetched {yielded} records for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')}")
                    time.sleep(0.3 + random.random() * 0.2) # 300-500ms sleep
                    break # Break retry loop on success
                except requests.exceptions.RequestException as e:
                    print(f"Attempt {i+1} failed for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')}: {e}")
                    time.sleep(0.5 * (2 ** i)) # Exponential backoff
                except Exception as e:
                    print(f"Error processing GDELT response for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')}: {e}")
                    break # Don't retry on parsing errors
            else:
                print(f"Warning: Failed to fetch data for {tech_id} {window_start_dt.strftime('%Y-%m-%d %H:%M')} after multiple retries.")

        current_day += timedelta(days=1)

