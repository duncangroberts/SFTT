"""Helpers to surface emerging technology keyword candidates from public chatter."""
from __future__ import annotations

import html
import json
import math
import re
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Set

import requests
from urllib.parse import urlparse

try:
    import db as database  # type: ignore
except ImportError:  # pragma: no cover - database module unavailable
    database = None  # type: ignore[assignment]

try:
    import spacy  # type: ignore
except ImportError:  # pragma: no cover - spaCy optional
    spacy = None  # type: ignore[assignment]

if spacy:
    from spacy.language import Language  # type: ignore
else:  # pragma: no cover - type hint fallback
    Language = None  # type: ignore[assignment]

try:
    from gdelt_fetch import build_query as gdelt_build_query  # type: ignore
except ImportError:  # pragma: no cover
    gdelt_build_query = None  # type: ignore[assignment]

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items/{story_id}"
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "Mozilla/5.0 (compatible; keyword-discovery/1.2)"

_SPACY_MODEL_NAME = "en_core_web_sm"
_POS_KEEP = {"NOUN", "PROPN"}

_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+\-/]*")
STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "about", "your",
    "have", "without", "within", "will", "would", "should", "their", "being", "were",
    "been", "over", "just", "more", "than", "when", "while", "these", "those", "after",
    "before", "under", "above", "between", "where", "which", "because", "during", "against",
    "among", "across", "around", "toward", "towards", "through", "throughout", "there",
    "here", "they", "them", "some", "such", "many", "each", "most", "very", "much", "like",
    "also", "using", "used", "use", "been", "what", "only", "even", "does", "done", "made",
    "make", "makes", "really", "into", "onto", "ever", "every", "still", "back", "take",
    "takes", "took", "going", "want", "wants", "need", "needs", "ever", "else", "than",
    "then", "out", "has", "had", "did", "why", "how", "who", "whom", "whose", "shall",
    "might", "could", "cant", "can't", "dont", "don't", "isnt", "isn't", "arent", "aren't",
    "wasnt", "wasn't", "werent", "weren't", "its", "it's", "im", "i'm", "ive", "i've",
    "you", "we", "our", "ours", "he", "she", "his", "her", "hers", "him", "via", "per",
    "towards", "again", "already", "around", "across", "another", "other", "others", "any",
    "either", "neither", "maybe", "perhaps", "into", "able", "almost", "seems", "seem",
    "seemed", "look", "looks", "looked", "looking", "said", "says", "say", "saying",
    "got", "get", "gets", "getting", "lot", "lots", "thing", "things", "something",
    "anything", "everything", "nothing", "people", "person", "someone", "anyone",
    "everyone", "month", "week", "year", "years", "today", "yesterday", "tomorrow",
    "news", "story", "stories", "article", "articles", "post", "posts", "thread", "threads",
}

SHORT_WHITELIST = {"ai", "xr", "vr", "ar", "ml", "llm", "gpu", "ev", "av", "nlp", "iot", "uv", "ux"}

_DEFAULT_TECH_BONUS_SUBSTRINGS = (
    "ai", "ml", "llm", "model", "agent", "quantum", "robot", "robotic", "fusion",
    "battery", "crypto", "chain", "block", "metaverse", "xr", "vr", "ar", "spatial",
    "neural", "cohere", "anthropic", "openai", "gpt", "compute", "chip", "silicon",
    "semiconductor", "photonic", "biotech", "genomic", "climate", "carbon",
    "autonomous", "drone", "satellite", "space", "wearable", "sensor", "edge", "cloud",
    "cyber", "security", "quant", "fintech", "robotics", "bio", "agritech", "energy",
)

NOVELTY_LOOKBACK_DAYS = 90
NOVELTY_THRESHOLD_RATIO = 1.25
NOVELTY_SCALING = 0.45
NOVELTY_MAX_MULTIPLIER = 1.8
NOVELTY_MIN_BASELINE = 1.0

_DISCOVERY_DIR = Path(__file__).resolve().parent
_GLOSSARY_PATH = _DISCOVERY_DIR / "tech_glossary.json"

_DEFAULT_GLOSSARY = {
    "bias_substrings": list(_DEFAULT_TECH_BONUS_SUBSTRINGS),
    "domains": {
        "Artificial Intelligence": [
            "ai", "artificial intelligence", "machine learning", "ml",
            "deep learning", "neural network", "generative ai", "large language model",
            "llm", "ai agent", "autonomous agent"
        ],
        "Robotics": [
            "robot", "robotics", "cobot", "automation", "autonomous system",
            "autonomous vehicle", "drone", "uav"
        ],
        "Quantum": [
            "quantum", "quantum computing", "qubit", "quantum supremacy"
        ],
        "Energy": [
            "battery", "fusion", "grid storage", "green hydrogen", "renewable",
            "energy storage"
        ],
        "Space": [
            "satellite", "launch vehicle", "spacecraft", "space tech", "orbital"
        ],
        "Security": [
            "cybersecurity", "zero trust", "secure enclave", "post-quantum", "threat intel"
        ],
        "Biotech": [
            "biotech", "genomics", "crispr", "synthetic biology", "bioinformatics"
        ],
        "Compute": [
            "gpu", "accelerator", "chip design", "silicon", "semiconductor", "photonic"
        ],
    },
}
_GLOSSARY_CACHE: Optional[dict] = None
_GLOSSARY_TOKENS: Optional[Set[str]] = None
_GLOSSARY_TOKEN_TO_DOMAIN: Optional[Dict[str, str]] = None
_TECH_BONUS_SUBSTRINGS: Tuple[str, ...] = _DEFAULT_TECH_BONUS_SUBSTRINGS
_NLP: Optional[Language] = None
_SPACY_READY: Optional[bool] = None
_SPACY_ERROR: Optional[str] = None


class KeywordDiscoveryError(RuntimeError):
    """Raised when the keyword discovery pipeline fails."""


def _log(logger: Optional[Callable[[str], None]], message: str) -> None:
    if logger:
        try:
            logger(message)
        except Exception:
            pass


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_token(token: str) -> Optional[str]:
    token = token.lower().strip("-+_")
    if not token:
        return None
    if token in STOPWORDS:
        return None
    if len(token) < 4 and token not in SHORT_WHITELIST:
        return None
    if token.isdigit():
        return None
    if not re.search("[a-z]", token):
        return None
    return token


def _extract_terms_basic(text: str) -> Tuple[List[str], List[str]]:
    tokens: List[str] = []
    for raw in _WORD_PATTERN.findall(text.lower()):
        cleaned = _clean_token(raw)
        if cleaned:
            tokens.append(cleaned)
    return tokens, []


def _ensure_spacy_pipeline(reload: bool = False) -> Optional[Language]:
    global _NLP, _SPACY_READY, _SPACY_ERROR
    if reload:
        _NLP = None
        _SPACY_READY = None
        _SPACY_ERROR = None
    if _NLP is not None:
        return _NLP
    if _SPACY_READY is False:
        return None
    if not spacy:
        _SPACY_READY = False
        _SPACY_ERROR = "spaCy not installed"
        return None
    try:
        nlp = spacy.load(_SPACY_MODEL_NAME, disable=["ner", "textcat"])  # type: ignore[arg-type]
        _NLP = nlp
        _SPACY_READY = True
        _SPACY_ERROR = None
        return nlp
    except Exception as exc:  # pragma: no cover - depends on external install
        _SPACY_READY = False
        _SPACY_ERROR = f"{type(exc).__name__}: {exc}"
        return None


def _extract_terms(text: str) -> Tuple[List[str], List[str]]:
    if not text:
        return [], []
    nlp = _ensure_spacy_pipeline()
    if not nlp:
        return _extract_terms_basic(text)
    try:
        doc = nlp(text)
    except Exception:  # pragma: no cover - runtime guard
        return _extract_terms_basic(text)
    tokens: List[str] = []
    phrases: Set[str] = set()

    for chunk in doc.noun_chunks:
        chunk_tokens: List[str] = []
        for token in chunk:
            cleaned = _clean_token(token.lemma_) or _clean_token(token.text)
            if cleaned:
                chunk_tokens.append(cleaned)
                tokens.append(cleaned)
        if len(chunk_tokens) >= 2:
            phrases.add(" ".join(chunk_tokens))

    for token in doc:
        if token.pos_ in _POS_KEEP:
            cleaned = _clean_token(token.lemma_) or _clean_token(token.text)
            if cleaned:
                tokens.append(cleaned)

    if not tokens and not phrases:
        return _extract_terms_basic(text)
    return tokens, sorted(phrases)


def _generate_bigrams(tokens: Sequence[str]) -> List[str]:
    if len(tokens) < 2:
        return []
    bigrams: List[str] = []
    for i in range(len(tokens) - 1):
        first, second = tokens[i], tokens[i + 1]
        if first in STOPWORDS or second in STOPWORDS:
            continue
        if first == second:
            continue
        bigrams.append(f"{first} {second}")
    return bigrams


def _tech_bias(term: str) -> float:
    for hint in _TECH_BONUS_SUBSTRINGS:
        if hint and hint in term:
            return 1.15
    return 1.0


def _comment_weight(points: int) -> float:
    if points <= 0:
        return 1.0
    return min(1.9, 1.0 + math.log1p(points) / 4.0)
def _register_term(registry: Dict[str, Dict[str, object]], term: str, origin: str, weight: float) -> None:
    if not term:
        return
    entry = registry.setdefault(term, {"weight": 1.0, "origins": set()})
    origins = entry.setdefault("origins", set())
    if isinstance(origins, set):
        origins.add(origin)
    else:  # pragma: no cover - defensive fallback
        new_set = set(origins)
        new_set.add(origin)
        entry["origins"] = new_set
        origins = new_set
    current_weight = float(entry.get("weight", 1.0))
    if weight > current_weight:
        entry["weight"] = float(weight)


def _load_glossary_config() -> dict:
    global _GLOSSARY_CACHE, _GLOSSARY_TOKENS, _GLOSSARY_TOKEN_TO_DOMAIN, _TECH_BONUS_SUBSTRINGS
    if _GLOSSARY_CACHE is not None:
        return _GLOSSARY_CACHE
    data: dict = {}
    if _GLOSSARY_PATH.exists():
        try:
            data = json.loads(_GLOSSARY_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if not data:
        data = json.loads(json.dumps(_DEFAULT_GLOSSARY))
    bias_values: List[str] = []
    for item in data.get("bias_substrings", []):
        s = str(item).strip().lower()
        if s:
            bias_values.append(s)
    _TECH_BONUS_SUBSTRINGS = tuple(bias_values) if bias_values else _DEFAULT_TECH_BONUS_SUBSTRINGS
    token_to_domain: Dict[str, str] = {}
    tokens: Set[str] = set()
    domains = data.get("domains", {})
    if isinstance(domains, dict):
        for domain_name, values in domains.items():
            if not isinstance(values, list):
                continue
            domain_label = str(domain_name)
            for raw in values:
                token = str(raw).strip().lower()
                if not token:
                    continue
                tokens.add(token)
                token_to_domain[token] = domain_label
    if not tokens:
        for domain_name, values in _DEFAULT_GLOSSARY["domains"].items():
            for token in values:
                tokens.add(token)
                token_to_domain[token] = domain_name
    _GLOSSARY_TOKENS = tokens
    _GLOSSARY_TOKEN_TO_DOMAIN = token_to_domain
    _GLOSSARY_CACHE = data
    return data


def _glossary_matches(text: str) -> Tuple[Set[str], Set[str]]:
    _load_glossary_config()
    tokens = _GLOSSARY_TOKENS or set()
    token_to_domain = _GLOSSARY_TOKEN_TO_DOMAIN or {}
    text_lower = text.lower()
    matched_tokens: Set[str] = set()
    for token in tokens:
        if not token:
            continue
        if " " in token or "-" in token or len(token) > 6:
            if token in text_lower:
                matched_tokens.add(token)
        else:
            pattern = rf"\\b{re.escape(token)}\\b"
            if re.search(pattern, text_lower):
                matched_tokens.add(token)
    matched_domains = {token_to_domain[tok] for tok in matched_tokens if tok in token_to_domain}
    return matched_tokens, matched_domains


def _fetch_comment_payloads(
    story_id: str,
    session: requests.Session,
    *,
    max_comments: int = 80,
    logger: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, object]]:
    url = ALGOLIA_ITEM_URL.format(story_id=story_id)
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        _log(logger, f"Discovery: comment fetch failed for {story_id}: {exc}")
        return []
    except ValueError:
        _log(logger, f"Discovery: comment JSON decode failed for {story_id}")
        return []

    payloads: List[Dict[str, object]] = []
    queue: deque[dict] = deque(data.get("children", []) or [])  # type: ignore[arg-type]
    while queue and len(payloads) < max_comments:
        node = queue.popleft()
        if not isinstance(node, dict):
            continue
        text = _strip_html(str(node.get("text") or ""))
        if not text:
            for child in node.get("children", []) or []:
                if isinstance(child, dict):
                    queue.append(child)
            continue
        raw_points = node.get("points")
        if raw_points is None:
            raw_points = node.get("score")
        try:
            points = int(raw_points or 0)
        except Exception:
            points = 0
        payloads.append({
            "text": text,
            "points": points,
            "weight": _comment_weight(points),
        })
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                queue.append(child)
    return payloads
def _gdelt_sources_for_term(
    term: str,
    *,
    days_back: int,
    max_records: int = 40,
    logger: Optional[Callable[[str], None]] = None,
) -> List[str]:
    if not gdelt_build_query:
        return []
    try:
        query = gdelt_build_query([term])  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - defensive
        _log(logger, f"GDELT query build failed for '{term}': {exc}")
        return []
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=max(days_back, 1))
    params = {
        "query": query,
        "mode": "artlist",
        "format": "JSON",
        "maxrecords": max_records,
        "startdatetime": start_dt.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end_dt.strftime("%Y%m%d%H%M%S"),
    }
    try:
        resp = requests.get(GDELT_DOC_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=18)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        _log(logger, f"GDELT sample failed for '{term}': {exc}")
        return []

    items = []
    if isinstance(data, dict):
        for key in ("articles", "artList", "articleList", "docs"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
    elif isinstance(data, list):
        items = data

    sources: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        src = (
            item.get("sourceCommonName")
            or item.get("SOURCECOMMONNAME")
            or item.get("source")
            or item.get("SOURCE")
        )
        if not src:
            url = item.get("sourceURL") or item.get("SOURCEURL") or item.get("url") or item.get("URL")
            if url:
                try:
                    netloc = urlparse(str(url)).netloc
                except Exception:
                    netloc = ""
                if netloc:
                    src = netloc.lower()
        if src:
            name = str(src).strip()
            if name:
                sources.append(name)
    seen: Set[str] = set()
    unique_sources: List[str] = []
    for src in sources:
        key = src.lower()
        if key not in seen:
            unique_sources.append(src)
            seen.add(key)
    return unique_sources
def _apply_novelty(
    candidates: List[Dict[str, object]],
    *,
    run_timestamp: datetime,
    lookback_days: int,
    logger: Optional[Callable[[str], None]] = None,
) -> None:
    if not database:
        for candidate in candidates:
            candidate["novelty_multiplier"] = 1.0
            candidate["baseline_mentions"] = 0.0
        return
    for candidate in candidates:
        term = candidate.get("term")
        if not term:
            candidate["novelty_multiplier"] = 1.0
            candidate["baseline_mentions"] = 0.0
            continue
        try:
            baseline = database.get_keyword_baseline(term, lookback_days, run_timestamp)
        except Exception as exc:  # pragma: no cover - db failure
            _log(logger, f"Discovery: baseline lookup failed for {term}: {exc}")
            candidate["novelty_multiplier"] = 1.0
            candidate["baseline_mentions"] = 0.0
            continue
        baseline_mentions = float((baseline or {}).get("avg_mentions") or 0.0)
        candidate["baseline_mentions"] = round(baseline_mentions, 2) if baseline_mentions else 0.0
        if baseline_mentions < NOVELTY_MIN_BASELINE:
            candidate["novelty_multiplier"] = 1.0
            continue
        mentions = candidate.get("mentions", 0)
        try:
            ratio = float(mentions) / baseline_mentions
        except Exception:
            ratio = 0.0
        if ratio <= NOVELTY_THRESHOLD_RATIO:
            candidate["novelty_multiplier"] = 1.0
            continue
        multiplier = min(NOVELTY_MAX_MULTIPLIER, 1.0 + (ratio - 1.0) * NOVELTY_SCALING)
        candidate["novelty_multiplier"] = round(multiplier, 2)
        candidate["score"] = round(float(candidate.get("score") or 0.0) * multiplier, 2)


def _record_keyword_history(
    candidates: List[Dict[str, object]],
    *,
    run_timestamp: datetime,
    window_days: int,
    logger: Optional[Callable[[str], None]] = None,
) -> None:
    if not database or not candidates:
        return
    try:
        database.record_keyword_mentions(
            entries=candidates,
            run_timestamp=run_timestamp,
            window_days=window_days,
        )
    except Exception as exc:  # pragma: no cover - db failure
        _log(logger, f"Discovery: failed to persist keyword history: {exc}")


def get_pos_backend_status(force_check: bool = False) -> Dict[str, object]:
    nlp = _ensure_spacy_pipeline(reload=force_check)
    return {
        "backend": "spaCy" if spacy else "builtin",
        "model": _SPACY_MODEL_NAME if nlp else None,
        "available": bool(nlp),
        "error": _SPACY_ERROR,
    }

def get_glossary_status() -> Dict[str, object]:
    """Return metadata about the loaded technology glossary."""
    _load_glossary_config()
    domains = sorted(set((_GLOSSARY_TOKEN_TO_DOMAIN or {}).values()))
    return {
        "path": str(_GLOSSARY_PATH),
        "token_count": len(_GLOSSARY_TOKENS or []),
        "domain_count": len(domains),
        "domains": domains,
    }

def discover_trending_keywords(
    *,
    days_back: int = 14,
    min_points: int = 50,
    top_n: int = 15,
    max_pages: int = 8,
    hits_per_page: int = 200,
    sleep_seconds: float = 0.25,
    include_comments: bool = True,
    max_comments_per_story: int = 80,
    confirm_with_gdelt: bool = False,
    novelty_lookback_days: int = NOVELTY_LOOKBACK_DAYS,
    max_gdelt_records: int = 40,
    logger: Optional[Callable[[str], None]] = None,
) -> Dict[str, object]:
    """Return candidate emerging-technology keywords mined from Hacker News chatter."""

    if days_back <= 0:
        raise ValueError("days_back must be positive")
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    now = datetime.now(timezone.utc)
    _load_glossary_config()
    pos_status = get_pos_backend_status()
    if pos_status.get("available"):
        _log(logger, f"Discovery: spaCy POS filtering active ({pos_status.get('model')})")
    else:
        _log(logger, f"Discovery: fallback tokens (spaCy unavailable: {pos_status.get('error') or 'not installed'})")
    _log(
        logger,
        f"Discovery: glossary gating with {len(_GLOSSARY_TOKENS or [])} tokens across {len((_GLOSSARY_TOKEN_TO_DOMAIN or {}).keys())} domains",
    )

    start_ts = int((now - timedelta(days=days_back)).timestamp())
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    candidates: Dict[str, Dict[str, object]] = {}
    total_hits = 0
    stories_considered = 0
    pages_fetched = 0

    try:
        for page in range(max_pages):
            params = {
                "tags": "story",
                "numericFilters": f"created_at_i>={start_ts}",
                "hitsPerPage": hits_per_page,
                "page": page,
            }
            _log(logger, f"Discovery: fetching page {page} ...")
            resp = session.get(ALGOLIA_SEARCH_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            hits: List[Dict[str, object]] = data.get("hits", [])  # type: ignore[assignment]
            total_hits += len(hits)
            pages_fetched += 1
            if not hits:
                break

            for hit in hits:
                try:
                    points = int(hit.get("points") or 0)
                    num_comments = int(hit.get("num_comments") or 0)
                except Exception:
                    points = int(hit.get("points") or 0)
                    num_comments = int(hit.get("num_comments") or 0)

                if points < min_points:
                    continue

                raw_title = (hit.get("title") or hit.get("story_title") or "").strip()
                title = _strip_html(raw_title)
                if not title:
                    continue

                created_at_i = int(hit.get("created_at_i") or 0)
                created_dt = datetime.fromtimestamp(created_at_i, tz=timezone.utc)
                url = (hit.get("url") or hit.get("story_url") or "").strip() or None
                story_id = str(hit.get("objectID") or "")

                title_tokens, title_phrases = _extract_terms(title)
                if not title_tokens and not title_phrases:
                    continue

                term_meta: Dict[str, Dict[str, object]] = {}
                for tok in title_tokens:
                    _register_term(term_meta, tok, "title", 1.0)
                title_bigrams = _generate_bigrams(title_tokens)
                for bigram in title_bigrams:
                    _register_term(term_meta, bigram, "title_bigram", 1.0)
                for phrase in title_phrases:
                    _register_term(term_meta, phrase, "title_phrase", 1.0)

                comment_payloads: List[Dict[str, object]] = []
                raw_comment_texts: List[str] = []
                if include_comments and story_id:
                    comment_payloads = _fetch_comment_payloads(
                        story_id,
                        session,
                        max_comments=max_comments_per_story,
                        logger=logger,
                    )
                    for payload in comment_payloads:
                        comment_text = payload.get("text") or ""
                        if not comment_text:
                            continue
                        raw_comment_texts.append(comment_text)
                        comment_tokens, comment_phrases = _extract_terms(comment_text)
                        weight = float(payload.get("weight") or 1.0)
                        if comment_tokens:
                            for tok in comment_tokens:
                                _register_term(term_meta, tok, "comment", weight)
                            for bigram in _generate_bigrams(comment_tokens):
                                _register_term(term_meta, bigram, "comment_bigram", weight)
                        if comment_phrases:
                            for phrase in comment_phrases:
                                _register_term(term_meta, phrase, "comment_phrase", weight)

                if not term_meta:
                    continue

                story_blob = " ".join([title] + raw_comment_texts)
                glossary_tokens, glossary_domains = _glossary_matches(story_blob)
                if not glossary_tokens:
                    continue

                quality = points + 0.35 * num_comments
                recency_days = max(0.0, (now - created_dt).total_seconds() / 86400.0)
                recency_weight = max(0.35, 1.0 - (recency_days / max(days_back, 1)))
                score_increment = quality * recency_weight

                story_info = {
                    "title": title,
                    "url": url,
                    "points": points,
                    "comments": num_comments,
                    "created_at": created_dt.isoformat(),
                    "id": story_id,
                    "quality": round(score_increment, 2),
                    "glossary_domains": sorted(glossary_domains),
                    "glossary_tokens": sorted(glossary_tokens)[:8],
                }

                stories_considered += 1
                for term, meta in term_meta.items():
                    entry = candidates.setdefault(
                        term,
                        {
                            "term": term,
                            "mentions": 0,
                            "score": 0.0,
                            "quality_sum": 0.0,
                            "top_stories": [],
                            "title_mentions": 0,
                            "comment_mentions": 0,
                            "glossary_tokens": set(),
                            "glossary_domains": set(),
                            "max_comment_weight": 1.0,
                        },
                    )
                    entry["mentions"] = int(entry.get("mentions") or 0) + 1
                    weight = float(meta.get("weight") or 1.0)
                    entry["score"] = float(entry.get("score") or 0.0) + score_increment * _tech_bias(term) * weight
                    entry["quality_sum"] = float(entry.get("quality_sum") or 0.0) + score_increment
                    origins = meta.get("origins") or set()
                    if any(str(o).startswith("comment") for o in origins):
                        entry["comment_mentions"] = int(entry.get("comment_mentions") or 0) + 1
                    if any(str(o).startswith("title") for o in origins):
                        entry["title_mentions"] = int(entry.get("title_mentions") or 0) + 1
                    entry["glossary_tokens"].update(glossary_tokens)  # type: ignore[attr-defined]
                    entry["glossary_domains"].update(glossary_domains)  # type: ignore[attr-defined]
                    entry["max_comment_weight"] = max(float(entry.get("max_comment_weight") or 1.0), weight)
                    top_stories: List[Dict[str, object]] = entry["top_stories"]  # type: ignore[assignment]
                    top_stories.append(story_info)
                    top_stories.sort(key=lambda s: s.get("quality", 0.0), reverse=True)
                    if len(top_stories) > 3:
                        top_stories[:] = top_stories[:3]

            nb_pages = int(data.get("nbPages") or 0)
            if page >= nb_pages - 1:
                break
            time.sleep(sleep_seconds)
    except requests.RequestException as exc:
        raise KeywordDiscoveryError(f"Failed to fetch Hacker News data: {exc}") from exc
    candidate_list: List[Dict[str, object]] = []
    for term, details in candidates.items():
        mentions = int(details.get("mentions") or 0)
        if mentions == 0:
            continue
        score = float(details.get("score") or 0.0)
        quality_sum = float(details.get("quality_sum") or 0.0)
        glossary_tokens = sorted(list(details.get("glossary_tokens") or []))
        glossary_domains = sorted(list(details.get("glossary_domains") or []))
        top_stories = [
            {
                "title": s.get("title"),
                "url": s.get("url"),
                "points": s.get("points"),
                "comments": s.get("comments"),
                "created_at": s.get("created_at"),
                "glossary_domains": s.get("glossary_domains"),
            }
            for s in details.get("top_stories", [])
        ]
        avg_quality = quality_sum / mentions if mentions else 0.0
        base_score = round(score, 2)
        candidate_list.append(
            {
                "term": term,
                "score": base_score,
                "base_score": base_score,
                "mentions": mentions,
                "avg_quality": round(avg_quality, 2),
                "title_mentions": int(details.get("title_mentions") or 0),
                "comment_mentions": int(details.get("comment_mentions") or 0),
                "max_comment_weight": round(float(details.get("max_comment_weight") or 1.0), 2),
                "glossary_tokens": glossary_tokens,
                "glossary_domains": glossary_domains,
                "top_stories": top_stories,
                "sample_title": top_stories[0]["title"] if top_stories else "",
                "sample_url": top_stories[0]["url"] if top_stories else None,
                "novelty_multiplier": 1.0,
                "baseline_mentions": 0.0,
                "gdelt_confirmed": None,
                "gdelt_sources": [],
            }
        )

    candidate_list.sort(key=lambda item: item["score"], reverse=True)

    _record_keyword_history(candidate_list, run_timestamp=now, window_days=days_back, logger=logger)
    _apply_novelty(candidate_list, run_timestamp=now, lookback_days=novelty_lookback_days, logger=logger)

    gdelt_checked_terms: List[str] = []
    if confirm_with_gdelt:
        gdelt_days = max(days_back, 7)
        for candidate in candidate_list[:top_n]:
            term = candidate.get("term")
            if not term:
                continue
            sources = _gdelt_sources_for_term(
                term,
                days_back=gdelt_days,
                max_records=max_gdelt_records,
                logger=logger,
            )
            candidate["gdelt_sources"] = sources
            candidate["gdelt_confirmed"] = len(sources) >= 2
            gdelt_checked_terms.append(str(term))

    top_candidates = candidate_list[:top_n]

    return {
        "generated_at": now.isoformat(),
        "days_back": days_back,
        "min_points": min_points,
        "stories_considered": stories_considered,
        "pages_fetched": pages_fetched,
        "total_hits": total_hits,
        "candidates": top_candidates,
        "include_comments": include_comments,
        "pos_backend": pos_status,
        "glossary_path": str(_GLOSSARY_PATH),
        "glossary_token_count": len(_GLOSSARY_TOKENS or []),
        "confirm_with_gdelt": confirm_with_gdelt,
        "gdelt_checked_terms": gdelt_checked_terms,
        "novelty_lookback_days": novelty_lookback_days,
    }
