#!/usr/bin/env python
"""Performs theme extraction and sentiment analysis."""

import os
import re
import spacy
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from sentence_transformers import SentenceTransformer

# Assuming llm_client is in the parent directory, and discover.src is in the python path
from llm_client import generate_completion

# --- Load Models ---
sentiment_analyzer = SentimentIntensityAnalyzer()

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

def get_merge_decision(new_theme, candidate_themes):
    """Asks the LLM to decide if a new theme should be merged into a candidate."""
    if not candidate_themes:
        return None

    candidate_names = [c['name'] for c in candidate_themes]
    
    system_prompt = (
        "You are a theme categorization expert. Your task is to determine if the 'new theme' fits well into one of the 'existing categories'."
        "If it is a good fit, respond with the exact name of the best matching category. Otherwise, respond with only the word 'None'."
    )

    prompt = (
        f"New theme: '{new_theme}'\n\n"
        f"Existing categories:\n"
        f"- {'\n- '.join(candidate_names)}\n\n"
        f"Which category is the best fit? If none are a good fit, say 'None'."
    )

    try:
        decision = generate_completion(
            prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=20 # Enough to return a theme name
        )
        decision = decision.strip().replace('"', '')

        if decision in candidate_names:
            # Find the full theme object that matches the name
            for theme in candidate_themes:
                if theme['name'] == decision:
                    return theme
        return None # If the LLM said 'None' or an invalid category

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


if __name__ == '__main__':
    # Example Usage
    sample_text = """
    A new study published in Nature demonstrates a breakthrough in using AI for medical diagnostics. 
    Researchers at a leading university have developed a deep learning model that can detect certain types of cancer 
    from medical images with higher accuracy than human radiologists. The study's authors believe this technology 
    could revolutionize the field, leading to earlier detection and better patient outcomes. However, they also 
    caution that ethical considerations and regulatory approval are significant hurdles that must be addressed.
    """

    # 1. Extract Theme
    print("1. Extracting Theme...")
    theme = extract_theme_from_text(sample_text)
    print(f"   - Extracted Theme: {theme}")

    # 2. Analyze Sentiment
    print("\n2. Analyzing Sentiment...")
    sentiment = get_sentiment_score(sample_text)
    print(f"   - Sentiment Score: {sentiment}")

    # 3. Generate Embedding
    if embedding_model:
        print("\n3. Generating Embedding...")
        embedding = get_embedding(theme)
        print(f"   - Embedding for '{theme}': {embedding[:5]}...")