#!/usr/bin/env python
"""Orchestrates the entire discovery pipeline."""

import numpy as np
import io
from sklearn.metrics.pairwise import cosine_similarity

from discover.src import hn_fetcher, content_processor, analysis, scoring, db_manager

SIMILARITY_THRESHOLD = 0.9 # Threshold for merging themes

def find_similar_themes(new_theme_name, new_theme_embedding, existing_themes, top_n=3):
    """Finds the top N most similar themes from a list of existing themes."""
    if new_theme_embedding is None or not existing_themes:
        return []

    new_embedding_reshaped = new_theme_embedding.reshape(1, -1)
    similarities = []

    for theme in existing_themes:
        if theme['embedding'] is None:
            continue
        
        out = io.BytesIO(theme['embedding'])
        out.seek(0)
        existing_embedding = np.load(out).reshape(1, -1)
        
        sim = cosine_similarity(new_embedding_reshaped, existing_embedding)[0][0]
        similarities.append((theme, sim))
    
    # Sort by similarity score in descending order and return the top N
    similarities.sort(key=lambda x: x[1], reverse=True)
    return [theme for theme, sim in similarities[:top_n]]

def run_discovery_pipeline(days=30, score_threshold=100, comments_threshold=50):
    """Runs the full pipeline to discover and score themes from Hacker News."""
    print("Starting Discovery Pipeline...")
    db_manager.setup_database() # Ensure DB is up to date

    # 1. Fetch top stories
    stories = hn_fetcher.fetch_stories_for_past_days(
        days=days, 
        score_threshold=score_threshold, 
        comments_threshold=comments_threshold
    )

    # Get all existing themes for similarity comparison
    existing_themes = db_manager.get_all_themes_with_embeddings()

    processed_count = 0
    for story in stories:
        story_id = story.get('id')
        if not story_id:
            continue

        # 2. Check if story has been processed
        if db_manager.is_story_processed(story_id):
            print(f"Skipping already processed story ID: {story_id}")
            continue

        print(f"\nProcessing story: {story.get('title')}")

        # 3. Fetch content
        story_url = story.get('url')
        story_content = content_processor.fetch_and_extract_text(story_url)
        
        comment_ids = story.get('kids', [])
        comments = hn_fetcher.get_comments(comment_ids)
        comment_texts = " \n".join([c.get('text', '') for c in comments])

        # Prepare a focused text block for theme extraction
        text_parts = [f"Title: {story.get('title', '')}"]
        if story_content:
            text_parts.append(f"Article excerpt: {story_content[:2000]}")
        if comment_texts:
            text_parts.append(f"Key discussions: {comment_texts[:1000]}")
        theme_extraction_text = "\n\n".join(text_parts)[:6000]

        if not theme_extraction_text.strip():
            print("Skipping story with no content.")
            db_manager.add_story(story_id, story.get('title', ''), story_url)
            continue

        # 4. Analyze content
        theme_name = analysis.extract_theme_from_text(theme_extraction_text)
        print(f"  - Extracted theme: {theme_name}")
        
        theme_embedding = analysis.get_embedding(theme_name)

        # 5. Get merge decision from LLM
        candidate_themes = find_similar_themes(theme_name, theme_embedding, existing_themes)
        merged_theme = analysis.get_merge_decision(theme_name, candidate_themes)
        
        if merged_theme:
            print(f"  - MERGE DECISION: LLM decided to merge '{merged_theme['name']}' into '{theme_name}'.")
            theme = merged_theme
        else:
            print(f"  - MERGE DECISION: LLM decided to create a new theme for '{theme_name}'.")
            theme = db_manager.get_or_create_theme(theme_name, theme_embedding)
            # Add the new theme to our in-memory list for this run
            if theme:
                existing_themes.append(theme)

        if not theme:
            print(f"  - CRITICAL: Could not find or create a theme for '{theme_name}'. Skipping story.")
            # Mark story as processed anyway to avoid retrying it
            db_manager.add_story(story_id, story.get('title', ''), story_url)
            continue

        sentiment_score = analysis.get_llm_sentiment_score(comment_texts)
        print(f"  - Sentiment score (LLM): {sentiment_score:.2f}")

        # 6. Calculate discussion score
        discussion_score = scoring.calculate_discussion_score(story)
        print(f"  - Discussion score: {discussion_score}")

        # 7. Update theme scores and trends
        old_sentiment_score = theme.get('sentiment_score', 0.0)
        if old_sentiment_score is None: old_sentiment_score = 0.0
        new_sentiment_score = (old_sentiment_score + sentiment_score) / 2 # Average the sentiment

        discussion_trend = 'rising' # Always rising when new discussion occurs
        sentiment_trend = scoring.determine_trend(old_sentiment_score, new_sentiment_score)
        
        db_manager.update_theme(
            theme_id=theme['id'],
            discussion_score=discussion_score,
            sentiment_score=new_sentiment_score,
            discussion_trend=discussion_trend,
            sentiment_trend=sentiment_trend
        )
        print(f"  - Updated theme '{theme['name']}' in the database.")

        # Link story to the theme
        db_manager.link_story_to_theme(story_id, theme['id'])

        # 8. Mark story as processed
        db_manager.add_story(story_id, story.get('title', ''), story_url)
        processed_count += 1

    print(f"\nDiscovery Pipeline finished. Processed {processed_count} new stories.")

if __name__ == '__main__':
    # Ensure the database is set up before running the pipeline
    db_manager.setup_database()
    run_discovery_pipeline(days=7, score_threshold=20, comments_threshold=10)