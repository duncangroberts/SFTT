
"""LLM-backed emerging theme discovery from Hacker News."""
from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import requests

import llm_runtime

from llm_client import LLMClientError, LlamaCppClient, generate_completion

DEFAULT_SYSTEM_PROMPT_TEMPLATE = """You are an emerging-technology intelligence analyst summarising Hacker News discussions.
Work only with the supplied dataset. Identify at most {max_themes} distinct themes.
Return a compact JSON object that looks exactly like this template:
{{
  "themes": [
    {{
      "title": "headline (<=80 chars)",
      "summary": "<=200 chars, one sentence",
      "why_it_matters": "<=200 chars, explain impact",
      "confidence": "high|medium|low",
      "signal_strength": "high|medium|low",
      "watch_actions": ["up to 3 bullets, each <=70 chars"],
      "signals": [
        {{
          "story_id": "story id from dataset",
          "insight": "<=160 chars describing the signal"
        }}
      ]
    }}
  ],
  "meta": {{
    "notes": "optional <=200 chars",
    "story_ids_included": ["ids you referenced"]
  }}
}}
Rules:
- Use ASCII only and escape double quotes.
- Keep every string within the stated limits.
- Lists must contain at most 3 items; use [] when empty.
- Do not invent story ids or facts; mark confidence low when uncertain.
- Output only the JSON object with no commentary or code fences."""

_PROMPTS_DIR = Path('prompts')
_SYSTEM_PROMPT_FILE = _PROMPTS_DIR / 'discovery_system_prompt.txt'

__all__ = [
    "generate_theme_report",
    "DiscoveryThemeError",
    "get_system_prompt_template",
    "save_system_prompt_template",
    "get_default_system_prompt_template",
    "get_system_prompt_path",
]

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
USER_AGENT = "Mozilla/5.0 (compatible; sftt-discovery/2.0)"
DISCUSSION_URL_TEMPLATE = "https://news.ycombinator.com/item?id={story_id}"

_JSON_BLOCK_RE = re.compile(rf"{chr(96)*3}(?:json)?\s*(.*?){chr(96)*3}", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

def get_default_system_prompt_template() -> str:
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE


def get_system_prompt_path() -> Path:
    return _SYSTEM_PROMPT_FILE



def get_system_prompt_template() -> str:
    try:
        return _SYSTEM_PROMPT_FILE.read_text(encoding='utf-8')
    except FileNotFoundError:
        return DEFAULT_SYSTEM_PROMPT_TEMPLATE


def save_system_prompt_template(template: str) -> None:
    cleaned = template.rstrip()
    if not cleaned:
        cleaned = DEFAULT_SYSTEM_PROMPT_TEMPLATE
    _PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    _SYSTEM_PROMPT_FILE.write_text(cleaned, encoding='utf-8')


def _render_system_prompt(max_themes: int, logger: Optional[Callable[[str], None]] = None) -> str:
    template = get_system_prompt_template()
    try:
        return template.format(max_themes=max_themes)
    except KeyError as exc:
        if logger:
            logger(f"System prompt template missing placeholder: {exc}; using default template")
    except Exception as exc:  # pragma: no cover
        if logger:
            logger(f"System prompt template error ({exc}); using default template")
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(max_themes=max_themes)





class DiscoveryThemeError(RuntimeError):
    """Raised when the LLM-backed discovery pipeline fails."""


def fetch_recent_hn_stories(
    *,
    days_back: int,
    min_points: int,
    max_pages: int = 6,
    hits_per_page: int = 100,
    max_stories: int = 80,
    max_prompt_stories: int = 40,
    sleep_seconds: float = 0.2,
    logger: Optional[Callable[[str], None]] = None,
) -> tuple[List[Dict[str, Any]], int]:
    """Fetch recent Hacker News stories meeting the filtering criteria."""

    if days_back <= 0:
        raise ValueError("days_back must be positive")
    if max_stories <= 0:
        raise ValueError("max_stories must be positive")
    if max_prompt_stories <= 0:
        raise ValueError("max_prompt_stories must be positive")

    now = datetime.now(timezone.utc)
    start_ts = int((now - timedelta(days=days_back)).timestamp())
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    stories: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    collection_target = max(max_stories, max_prompt_stories) * 2

    for page in range(max_pages):
        params = {
            "tags": "story",
            "numericFilters": f"created_at_i>={start_ts}",
            "hitsPerPage": hits_per_page,
            "page": page,
        }
        if logger:
            logger(f"LLM discovery: fetching HN page {page}")
        try:
            response = session.get(ALGOLIA_SEARCH_URL, params=params, timeout=20)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise DiscoveryThemeError(f"Failed to fetch Hacker News page {page}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DiscoveryThemeError(f"Invalid JSON from Algolia response on page {page}: {exc}") from exc

        hits = payload.get("hits") or []
        if not hits:
            break

        for hit in hits:
            story_id = str(hit.get("objectID") or "").strip()
            if not story_id or story_id in seen_ids:
                continue
            title = _strip_html((hit.get("title") or hit.get("story_title") or "").strip())
            if not title:
                continue
            try:
                points = int(hit.get("points") or 0)
            except Exception:
                points = 0
            if points < min_points:
                continue
            try:
                num_comments = int(hit.get("num_comments") or 0)
            except Exception:
                num_comments = 0

            created_at_i = int(hit.get("created_at_i") or 0)
            created_dt = datetime.fromtimestamp(created_at_i, tz=timezone.utc)

            url = (hit.get("url") or hit.get("story_url") or "").strip()
            domain = urlparse(url).netloc.lower() if url else ""

            story_text = _strip_html(hit.get("story_text") or "")
            if not story_text:
                highlight = hit.get("_highlightResult") or {}
                if isinstance(highlight, dict):
                    highlight_story = highlight.get("story_text")
                    if isinstance(highlight_story, dict):
                        story_text = _strip_html(highlight_story.get("value") or "")

            author = str(hit.get("author") or "").strip()
            score = float(points) + float(num_comments) * 0.5

            stories.append(
                {
                    "id": story_id,
                    "title": title,
                    "url": url,
                    "domain": domain,
                    "points": points,
                    "comments": num_comments,
                    "created_at": created_dt.isoformat(),
                    "created_at_ts": created_at_i,
                    "summary": story_text,
                    "author": author,
                    "discussion_url": DISCUSSION_URL_TEMPLATE.format(story_id=story_id),
                    "score": score,
                }
            )
            seen_ids.add(story_id)

            if len(stories) >= collection_target:
                break
        if len(stories) >= collection_target:
            break
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    stories.sort(key=lambda s: (s.get("score", 0.0), s.get("created_at_ts", 0)), reverse=True)
    total_relevant = len(stories)
    trimmed = stories[:max_stories]
    for story in trimmed:
        story.pop("created_at_ts", None)
    return trimmed, total_relevant


def generate_theme_report(
    *,
    days_back: int = 7,
    min_points: int = 40,
    max_themes: int = 5,
    max_stories: int = 60,
    max_prompt_stories: int = 30,
    temperature: float = 0.1,
    top_p: float = 0.8,
    max_tokens: int = 600,
    logger: Optional[Callable[[str], None]] = None,
    auto_manage_server: bool = True,
) -> Dict[str, Any]:
    """Generate emerging technology themes using the local llama.cpp model."""

    if days_back <= 0:
        raise ValueError("days_back must be positive")
    if max_themes <= 0:
        raise ValueError("max_themes must be positive")

    try:
        stories, total_relevant = fetch_recent_hn_stories(
            days_back=days_back,
            min_points=min_points,
            max_stories=max_stories,
            max_prompt_stories=max_prompt_stories,
            logger=logger,
        )
    except DiscoveryThemeError:
        raise
    except requests.RequestException as exc:
        raise DiscoveryThemeError(f"Failed to fetch Hacker News data: {exc}") from exc

    if not stories:
        raise DiscoveryThemeError("No Hacker News stories met the filters.")

    prompt_stories = stories[:max_prompt_stories]
    story_lookup = {story["id"]: story for story in prompt_stories}
    system_prompt = _render_system_prompt(max_themes, logger=logger)
    prompt = _build_prompt(prompt_stories, days_back)

    client = LlamaCppClient()

    if logger:
        logger(
            f"LLM discovery: analysing {len(prompt_stories)} stories for up to {max_themes} themes"
        )

    raw_output = ""
    parsed: Optional[Dict[str, Any]] = None
    try:
        ctx = llm_runtime.manage_llama_server(client=client, logger=logger, auto_start=auto_manage_server)
        with ctx:
            raw_output = generate_completion(
                prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                client=client,
            )
            try:
                parsed = _extract_json_object(raw_output)
            except DiscoveryThemeError as exc:
                if logger:
                    preview = raw_output.strip()[:1500]
                    logger(f"LLM output (truncated 1500 chars): {preview}")
                    logger("Attempting JSON repair via LLM")
                parsed = _attempt_repair_json(
                    raw_output,
                    client=client,
                    logger=logger,
                    max_tokens=max_tokens,
                )
                if parsed is None:
                    raise
    except llm_runtime.LlamaServerError as exc:
        raise DiscoveryThemeError(f"Failed to start llama.cpp server: {exc}") from exc
    except LLMClientError as exc:
        raise DiscoveryThemeError(f"Local LLM call failed: {exc}") from exc

    if parsed is None:
        raise DiscoveryThemeError("LLM did not return any themes.")
    raw_themes = parsed.get("themes")
    themes = _normalise_themes(raw_themes, story_lookup)
    if not themes:
        raise DiscoveryThemeError("LLM did not return any themes.")

    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "days_back": days_back,
        "min_points": min_points,
        "max_themes": max_themes,
        "stories_considered": total_relevant,
        "stories_in_prompt": len(prompt_stories),
        "themes": themes,
        "stories": stories,
        "generated_at": generated_at,
        "raw_output": raw_output,
        "raw_payload": parsed,
    }


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _shorten(text: str, limit: int = 220) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    trimmed = text[: limit - 3].rsplit(" ", 1)[0]
    return f"{trimmed}..."


def _build_prompt(stories: Sequence[Dict[str, Any]], days_back: int) -> str:
    lines: List[str] = []
    lines.append(
        f"Dataset: Hacker News frontier technology stories from the last {days_back} days."
    )
    lines.append(
        "Each entry is id | points | comments | domain | title | signal snippet. Focus on emerging tech and science themes."
    )
    lines.append("")
    lines.append("Stories:")
    for story in stories:
        snippet = _shorten(story.get("summary") or "")
        domain = story.get("domain") or "news.ycombinator.com"
        lines.append(
            f"{story['id']} | {story['points']} pts | {story['comments']} comments | {domain} | {story['title']}"
        )
        lines.append(
            f"Published: {story.get('created_at', '')} | Discussion: {story.get('discussion_url', '')}"
        )
        if snippet:
            lines.append(f"Signal: {snippet}")
        lines.append("")
    lines.append("Return JSON as instructed above.")
    return "\n".join(lines).strip()








def _escape_unescaped_whitespace(snippet: str) -> str:
    result: list[str] = []
    in_string = False
    escape = False
    for ch in snippet:
        if in_string:
            if escape:
                result.append(ch)
                escape = False
                continue
            if ch == "\\":
                result.append(ch)
                escape = True
                continue
            if ch == "\"":
                result.append(ch)
                in_string = False
                continue
            if ch == "\n":
                result.append("\\n")
                continue
            if ch == "\r":
                result.append("\\r")
                continue
            if ch == "\t":
                result.append("\\t")
                continue
            result.append(ch)
        else:
            result.append(ch)
            if ch == "\"":
                in_string = True
    return "".join(result)



def _try_parse_json(text: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    cleaned = text.strip()
    match = _JSON_BLOCK_RE.search(cleaned)
    if match:
        cleaned = match.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "LLM response did not contain JSON content."
    snippet = cleaned[start : end + 1]
    snippet = _escape_unescaped_whitespace(snippet)
    try:
        return json.loads(snippet), None
    except json.JSONDecodeError as exc:
        return None, f"LLM JSON decode failed: {exc}"


def _extract_json_object(text: str) -> Dict[str, Any]:
    parsed, error = _try_parse_json(text)
    if parsed is None:
        raise DiscoveryThemeError(error or "LLM JSON decode failed.")
    return parsed






def _attempt_repair_json(
    raw_output: str,
    *,
    client: LlamaCppClient,
    logger: Optional[Callable[[str], None]],
    max_tokens: int,
) -> Optional[Dict[str, Any]]:
    snippet = raw_output.strip()
    if not snippet:
        return None
    clip = snippet if len(snippet) <= 6000 else snippet[:6000]
    repair_prompt = (
        "You are a JSON repair assistant. You receive text that was intended to match this schema: "
        '{"themes": [...], "meta": {...}}. '
        "Fix structural issues (missing commas, stray text, invalid escape sequences) and respond "
        "with valid JSON only. Do not add explanations or code fences."
    )
    prompt = (
        "Make this JSON valid according to the schema.\n\n"
        f"Input:\n{clip}"
    )
    try:
        fixed = generate_completion(
            prompt,
            system_prompt=repair_prompt,
            temperature=0.0,
            top_p=0.0,
            max_tokens=max_tokens,
            client=client,
        )
    except LLMClientError as exc:
        if logger:
            logger(f"JSON repair call failed: {exc}")
        return None
    parsed, error = _try_parse_json(fixed)
    if parsed is None and logger:
        preview = fixed.strip()[:1200]
        logger(error or "JSON repair still invalid")
        logger(f"Repair attempt output (truncated 1200 chars): {preview}")
    return parsed


def _normalise_themes(raw_themes: Any, story_lookup: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    themes: List[Dict[str, Any]] = []
    if not isinstance(raw_themes, list):
        return themes

    for idx, item in enumerate(raw_themes, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("theme") or "").strip()
        summary = str(item.get("summary") or item.get("description") or "").strip()
        why = str(item.get("why_it_matters") or item.get("implication") or summary).strip()
        confidence = _normalise_level(item.get("confidence"))
        strength = _normalise_level(item.get("signal_strength") or item.get("momentum") or confidence)
        watch_actions = _coerce_str_list(item.get("watch_actions") or item.get("next_steps"))

        signals_data = item.get("signals") or []
        signals: List[Dict[str, Any]] = []
        referenced_ids: set[str] = set()
        if isinstance(signals_data, list):
            for sig in signals_data:
                if not isinstance(sig, dict):
                    continue
                story_id = str(sig.get("story_id") or sig.get("id") or "").strip()
                if not story_id:
                    continue
                referenced_ids.add(story_id)
                story = story_lookup.get(story_id)
                insight = str(
                    sig.get("insight")
                    or sig.get("note")
                    or sig.get("rationale")
                    or (story["title"] if story else "")
                ).strip()
                signals.append(
                    {
                        "story_id": story_id,
                        "headline": story["title"] if story else "",
                        "insight": insight,
                    }
                )

        extra_ids = item.get("story_ids") or item.get("evidence_ids") or []
        if isinstance(extra_ids, list):
            for sid in extra_ids:
                sid_str = str(sid).strip()
                if sid_str:
                    referenced_ids.add(sid_str)

        story_refs: List[Dict[str, Any]] = []
        for sid in referenced_ids:
            story = story_lookup.get(sid)
            if story:
                story_refs.append(story)

        domains: List[str] = []
        raw_domains = item.get("domains") or item.get("categories") or []
        if isinstance(raw_domains, list):
            for dom in raw_domains:
                dom_str = str(dom).strip()
                if dom_str:
                    domains.append(dom_str)

        themes.append(
            {
                "title": title or f"Theme {idx}",
                "summary": summary,
                "why_it_matters": why,
                "confidence": confidence,
                "signal_strength": strength,
                "watch_actions": watch_actions,
                "signals": signals,
                "story_refs": story_refs,
                "domains": domains,
                "raw": item,
            }
        )

    return themes


def _normalise_level(value: Any) -> str:
    if not value:
        return "medium"
    text = str(value).strip().lower()
    if text in {"high", "medium", "low"}:
        return text
    if text in {"very high", "strong", "elevated", "robust"}:
        return "high"
    if text in {"weak", "very low", "uncertain"}:
        return "low"
    return "medium"


def _coerce_str_list(value: Any) -> List[str]:
    results: List[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                item = item.strip()
                if item:
                    results.append(item)
    elif isinstance(value, str):
        text = value.strip()
        if text:
            results.append(text)
    return results
