import time
import math
import re
from datetime import datetime, timezone
from typing import Iterable, Tuple

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore


ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HN_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; hn-sentiment/1.0)"}
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"


def _strip_html(text: str) -> str:
    if not text:
        return ""
    # Basic HTML entity and tag stripping
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[^;]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _combine_patterns(patterns: list[str]) -> str:
    pats = [p.strip() for p in patterns if p and p.strip()]
    if not pats:
        return ""
    # Quote any term with non-alphanumeric chars (spaces, hyphens, etc.)
    quoted = [f'"{p}"' if re.search(r"[^A-Za-z0-9]", p) else p for p in pats]
    # Build OR query wrapped in parentheses; requires advancedSyntax=true on Algolia
    return "(" + " OR ".join(quoted) + ")"


def search_story_ids(patterns: list[str], start_ts: int, end_ts: int, max_hits: int = 500, logger=None) -> list[int]:
    """Search HN stories via Algolia between timestamps inclusive, per-term union.

    Iterates each subterm individually and unions results across terms. Limits to max_hits total.
    """
    if requests is None:
        return []

    ids: list[int] = []
    seen: set[int] = set()
    per_page = 100
    pats = [p.strip() for p in patterns if p and p.strip()]
    if not pats:
        pats = ["*"]

    for p in pats:
        q = f'"{p}"' if re.search(r"[^A-Za-z0-9]", p) else p
        page = 0
        contributed = 0
        while len(ids) < max_hits:
            try:
                params = {
                    "query": q or "*",
                    "tags": "story",
                    "numericFilters": f"created_at_i>={start_ts},created_at_i<={end_ts}",
                    "hitsPerPage": per_page,
                    "page": page,
                    "advancedSyntax": "true",
                }
                if logger and page == 0:
                    try:
                        preq = requests.Request('GET', ALGOLIA_SEARCH_URL, params=params).prepare()
                        logger(f"HN: term '{p}' GET {preq.url}")
                    except Exception:
                        logger(f"HN: term '{p}' page0")
                r = requests.get(ALGOLIA_SEARCH_URL, params=params, headers=HN_HEADERS, timeout=15)
                r.raise_for_status()
                data = r.json()
                hits = data.get("hits", [])
                if logger and page == 0:
                    nb_hits = data.get("nbHits")
                    nb_pages = data.get("nbPages")
                    logger(f"HN: term '{p}' nbHits={nb_hits}, nbPages={nb_pages}, hits_page0={len(hits)}")
                if not hits:
                    break
                for h in hits:
                    try:
                        sid = int(h.get("objectID"))
                        if sid not in seen:
                            seen.add(sid)
                            ids.append(sid)
                            contributed += 1
                        if len(ids) >= max_hits:
                            break
                    except Exception:
                        continue
                page += 1
                time.sleep(0.2)
            except Exception:
                if logger:
                    logger(f"HN: error fetching term '{p}' page {page}; stopping this term")
                break
        if logger:
            logger(f"HN: term '{p}' contributed {contributed} stories (total {len(ids)})")
        if len(ids) >= max_hits:
            break
    return ids


def fetch_comments_texts(story_id: int, max_comments: int = 300, logger=None) -> list[str]:
    """Fetches comment texts (shallow) for a story via the official Firebase API.

    Traverses the first-level kids and collects their text if not deleted/dead.
    """
    if requests is None:
        return []
    texts: list[str] = []
    try:
        s = requests.get(HN_ITEM_URL.format(id=story_id), timeout=15)
        s.raise_for_status()
        story = s.json() or {}
        kids = story.get("kids") or []
        for kid_id in kids:
            if len(texts) >= max_comments:
                break
            try:
                c = requests.get(HN_ITEM_URL.format(id=kid_id), timeout=15)
                c.raise_for_status()
                item = c.json() or {}
                if item.get("dead") or item.get("deleted"):
                    continue
                txt = _strip_html(item.get("text") or "")
                if txt:
                    texts.append(txt)
            except Exception:
                continue
            time.sleep(0.05)
    except Exception:
        if logger:
            logger(f"HN: failed to fetch story {story_id}; skipping its comments")
        return texts
    return texts


def _simple_compound(text: str) -> float:
    """Very small lexicon-based fallback compound score in [-1, 1]."""
    pos = {
        'good','great','excellent','amazing','love','like','awesome','positive','benefit','beneficial',
        'win','success','improve','improved','improving','fast','faster','best','cool','wow','brilliant','promising'
    }
    neg = {
        'bad','terrible','awful','hate','dislike','worse','worst','problem','bug','slow','scam','risk','risky',
        'fail','failure','broken','stupid','useless','garbage','sucks','concern','concerns','concerned','issue','issues'
    }
    # crude tokenization
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    if not tokens:
        return 0.0
    # handle simple negation: invert polarity of next token if preceded by a negation word
    negators = {'not', "isn't", "don't", "doesn't", "didn't", "no", "never", "can't", "won't"}
    score = 0
    i = 0
    while i < len(tokens):
        t = tokens[i]
        invert = t in negators
        if invert and i + 1 < len(tokens):
            nxt = tokens[i+1]
            if nxt in pos:
                score -= 1
                i += 2
                continue
            if nxt in neg:
                score += 1
                i += 2
                continue
        if t in pos:
            score += 1
        elif t in neg:
            score -= 1
        i += 1
    # normalize to [-1, 1]
    denom = max(1, len(tokens) // 5)  # scale softly with length
    comp = max(-1.0, min(1.0, score / denom))
    return comp


def analyse_sentiment_vader(texts: Iterable[str], logger=None) -> Tuple[float | None, int]:
    """Returns (avg_compound, count) using VADER over the given texts.

    If vaderSentiment is unavailable or no texts, returns (None, 0).
    """
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except Exception as e:
        if logger:
            logger(f"HN: VADER import failed: {e}")
        # Fallback to simple lexicon-based sentiment
        comps: list[float] = []
        for t in texts:
            try:
                c = _simple_compound(t)
            except Exception:
                c = 0.0
            comps.append(c)
        if not comps:
            if logger:
                logger("HN: vaderSentiment not installed and no texts; skipping HN sentiment")
            return None, 0
        avg = sum(comps) / len(comps)
        if logger:
            logger("HN: using simple fallback sentiment (install vaderSentiment for better accuracy)")
        return avg, len(comps)

    analyzer = SentimentIntensityAnalyzer()
    if logger:
        try:
            # Python 3.8+: importlib.metadata
            try:
                from importlib.metadata import version
            except Exception:
                from importlib_metadata import version  # type: ignore
            v = None
            try:
                v = version('vaderSentiment')
            except Exception:
                pass
            logger(f"HN: using VADER sentiment{(' v'+v) if v else ''}")
        except Exception:
            logger("HN: using VADER sentiment")
    compounds: list[float] = []
    for t in texts:
        try:
            if not t:
                continue
            s = analyzer.polarity_scores(t)
            compounds.append(float(s.get("compound", 0.0)))
        except Exception:
            continue

    if not compounds:
        return None, 0
    avg = sum(compounds) / len(compounds)
    if logger:
        try:
            pos = len([c for c in compounds if c > 0.05])
            neg = len([c for c in compounds if c < -0.05])
            neu = len(compounds) - pos - neg
            logger(f"HN: VADER stats n={len(compounds)} avg={avg:.3f} min={min(compounds):.3f} max={max(compounds):.3f} pos/neu/neg={pos}/{neu}/{neg}")
        except Exception:
            pass
    return avg, len(compounds)


def compute_month_score(patterns: list[str], start_dt: datetime, end_dt: datetime, logger=None) -> tuple[float | None, int, float | None]:
    """Computes the Hacker News score for the date window.

    Returns (hn_score_0_100 or None, comment_count, avg_compound or None).
    """
    # Ensure UTC timestamps
    start_ts = int(start_dt.replace(tzinfo=timezone.utc).timestamp())
    end_ts = int(end_dt.replace(tzinfo=timezone.utc).timestamp())

    story_ids = search_story_ids(patterns, start_ts, end_ts, max_hits=400, logger=logger)
    if not story_ids:
        if logger:
            logger("HN: no stories found for month window")
        return None, 0, None

    all_texts: list[str] = []
    for sid in story_ids:
        texts = fetch_comments_texts(sid, max_comments=200, logger=logger)
        if texts:
            all_texts.extend(texts)
        # modest pacing
        time.sleep(0.05)

    if logger:
        logger(f"HN: aggregated {len(all_texts)} comments across {len(story_ids)} stories")
    avg_compound, count = analyse_sentiment_vader(all_texts, logger=logger)
    if avg_compound is None or count == 0:
        if logger:
            logger("HN: no valid comments or sentiment analysis unavailable; score will be blank")
        return None, 0, None

    # Map -1..1 -> 0..100
    hn_score = ((avg_compound + 1.0) / 2.0) * 100.0
    # clamp 0..100
    hn_score = max(0.0, min(100.0, hn_score))
    if logger:
        logger(f"HN: avg compound {avg_compound:.3f} -> score {hn_score:.1f} from {count} comments")
    return hn_score, count, avg_compound
