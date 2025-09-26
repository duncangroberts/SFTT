#!/usr/bin/env python
"""Performs theme extraction and sentiment analysis."""

import os
import re
from sentence_transformers import SentenceTransformer

# Assuming llm_client is in the parent directory, and discover.src is in the python path
from llm_client import generate_completion

# --- Load Models ---

# The path to the model is relative to the project root
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'models', 'all-MiniLM-L6-v2')

if os.path.exists(MODEL_PATH):
    embedding_model = SentenceTransformer(MODEL_PATH)
else:
    print(f"Warning: Embedding model not found at {MODEL_PATH}. Trying to load from Hugging Face.")
    try:
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    except Exception as e:
        print(f"Fatal: Could not load embedding model. {e}")
        embedding_model = None

def validate_and_clean_theme(theme):
    """Validate and potentially reject themes."""
    if not theme:
        return None

    # Check for overly generic words
    too_generic = {'technology', 'software', 'computer', 'internet', 'digital', 'data'}
    theme_words = set(theme.lower().split())
    
    if len(theme_words) == 1 and theme_words.issubset(too_generic):
        return None  # Reject

    # Add more validation rules here if needed
    
    return theme

def extract_theme_from_text(text_content):
    """Enhanced theme extraction for more capable models like Llama 3.1."""
    if not text_content:
        return "Uncategorized"

    system_prompt = ("""You are a technical content categorization expert. Your task is to identify the primary theme of discussions in a way that balances specificity with generality.

Think of themes as "folders" where similar discussions would naturally group together. Each folder should:
- Contain 5-15 similar discussions when applied across a large dataset
- Be specific enough to be insightful (not "Technology News")  
- Be general enough to recur over time (not "GPT-4 Released")
- Focus on patterns, problems, approaches, or trends

Before answering, consider:
1. What is the core issue or pattern being discussed?
2. Will this same theme likely appear in other discussions?
3. Is this specific enough to be meaningful but general enough to recur?

Output only the theme as a 2-5 word noun phrase.""")

    try:
        theme = generate_completion(
            text_content, # The text is already prepared by the pipeline
            system_prompt=system_prompt,
            temperature=0.35,
            top_p=0.9,
            top_k=40, # top_k is supported by our updated client
            repeat_penalty=1.2,
            max_tokens=20,
            stop=['\n']
        )
        
        cleaned_theme = theme.strip().replace('"', '').replace('.', '')
        validated_theme = validate_and_clean_theme(cleaned_theme)

        if validated_theme:
            return validated_theme
        else:
            print(f"Invalid or too generic theme generated: '{cleaned_theme}'. Falling back.")
            return "Uncategorized"

    except Exception as e:
        print(f"Error during theme extraction: {e}")
        return "Uncategorized"

def get_merge_decision(new_theme, candidate_matches, min_similarity=0.6):
    """Uses the LLM to decide if the proposed theme matches an existing one."""
    if not candidate_matches:
        return None

    best_similarity = max((match.get('similarity', 0.0) for match in candidate_matches), default=0.0)
    if best_similarity < min_similarity:
        return None

    candidate_lines = []
    candidate_map = {}
    for index, match in enumerate(candidate_matches, start=1):
        theme = match.get('theme') or {}
        name = theme.get('name')
        if not name:
            continue

        candidate_map[name] = theme
        similarity = match.get('similarity', 0.0)
        titles = match.get('example_titles') or []
        display_titles = '; '.join(titles[:3]) if titles else 'No linked stories yet.'
        candidate_lines.append(
            f"{index}. {name}\n   similarity: {similarity:.2f}\n   example stories: {display_titles}"
        )

    if not candidate_lines:
        return None

    system_prompt = (
        "You group Hacker News discussions into reusable themes. "
        "Merge the proposal into an existing theme only when it clearly refers to the same recurring topic. "
        "Respond with 'None' whenever the match is uncertain."
    )

    prompt = (
        f"Proposed theme: {new_theme}\n\n"
        "Candidate themes with similar embeddings:\n"
        f"{'\n'.join(candidate_lines)}\n\n"
        "Respond with the exact name of the best matching existing theme. "
        "If none align closely, answer with the single word None."
    )

    try:
        decision = generate_completion(
            prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=32
        )
        decision_text = decision.strip().strip('"').strip("'")

        if not decision_text:
            return None

        if 'none' in decision_text.lower():
            return None

        if decision_text in candidate_map:
            return candidate_map[decision_text]

        for name, theme in candidate_map.items():
            if decision_text.lower() == name.lower():
                return theme

        tokens = decision_text.split()
        if tokens and tokens[0].isdigit():
            index = int(tokens[0])
            if 1 <= index <= len(candidate_matches):
                matched = candidate_matches[index - 1].get('theme')
                if matched:
                    return matched

        return None

    except Exception as e:
        print(f"Error during merge decision: {e}")
        return None



def get_embedding(text):
    """Generates an embedding for a given text."""
    if not embedding_model or not text:
        return None
    return embedding_model.encode(text)

def get_llm_sentiment_score(text_content):
    """Uses an LLM to analyze sentiment and return a score between -1 and 1."""
    if not text_content:
        return 0.0

    max_length = 4000
    truncated_content = text_content[:max_length]

    system_prompt = (
        "You are a sentiment analysis expert. Analyze the sentiment of the provided text. "
        "Your response MUST be a single floating-point number between -1.0 (very negative) and 1.0 (very positive). "
        "DO NOT include any other words, symbols, or explanations. Just the number."
    )

    prompt = f"Text to analyze:\n\n---\n{truncated_content}\n---\n\nSentiment score:"

    try:
        response_text = generate_completion(prompt, system_prompt=system_prompt, max_tokens=10, temperature=0.0)
        
        # First, try to find a float with regex
        match = re.search(r'-?\d+\.?\d*', response_text)
        if match:
            try:
                score = float(match.group(0))
                return max(-1.0, min(1.0, score)) # Clamp the score
            except (ValueError, TypeError):
                pass # Fall through to the next attempt

        # If regex fails, try a more direct conversion
        try:
            return float(response_text.strip())
        except (ValueError, TypeError):
            print(f"Could not parse float from sentiment response: '{response_text}'")
            return 0.0

    except Exception as e:
        print(f"Error during LLM sentiment analysis: {e}")
        return 0.0


