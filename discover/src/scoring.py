#!/usr/bin/env python
"""Calculates discussion and sentiment scores."""

import datetime

def calculate_discussion_score(story):
    """Calculates a discussion score based on upvotes and comments."""
    # Weighted score: comments are a stronger indicator of engagement.
    score = story.get('score', 0)
    comment_count = story.get('descendants', 0)
    return score + (comment_count * 2)

def determine_trend(old_score, new_score, threshold=0.1):
    """Determines the trend of a score."""
    if new_score > old_score + threshold:
        return "rising"
    if new_score < old_score - threshold:
        return "falling"
    return "stable"

def update_theme_lifecycle(theme, inactivity_days=14):
    """Checks if a theme should be marked as 'dying' due to inactivity."""
    # This function is intended to be called periodically on all themes.
    # For now, we can simulate this check when a theme is retrieved.
    last_updated_str = theme.get('updated_at')
    if last_updated_str:
        last_updated_date = datetime.datetime.fromisoformat(last_updated_str)
        if (datetime.datetime.now() - last_updated_date).days > inactivity_days:
            return "dying"
    return theme.get('discussion_score_trend', 'stable')

if __name__ == '__main__':
    # Example Usage
    sample_story = {'score': 150, 'descendants': 75}

    # 1. Calculate Discussion Score
    print("1. Calculating Discussion Score...")
    discussion_score = calculate_discussion_score(sample_story)
    print(f"   - Score: {sample_story['score']}, Comments: {sample_story['descendants']}")
    print(f"   - Calculated Discussion Score: {discussion_score}")

    # 2. Determine Trend
    print("\n2. Determining Trend...")
    old_sentiment = 0.5
    new_sentiment = 0.8
    trend = determine_trend(old_sentiment, new_sentiment)
    print(f"   - Old: {old_sentiment}, New: {new_sentiment} => Trend: {trend}")

    old_sentiment = 0.5
    new_sentiment = 0.2
    trend = determine_trend(old_sentiment, new_sentiment)
    print(f"   - Old: {old_sentiment}, New: {new_sentiment} => Trend: {trend}")

    old_sentiment = 0.5
    new_sentiment = 0.55
    trend = determine_trend(old_sentiment, new_sentiment)
    print(f"   - Old: {old_sentiment}, New: {new_sentiment} => Trend: {trend}")

    # 3. Theme Lifecycle
    print("\n3. Checking Theme Lifecycle...")
    fourteen_days_ago = (datetime.datetime.now() - datetime.timedelta(days=15)).isoformat()
    active_theme = {'updated_at': datetime.datetime.now().isoformat(), 'discussion_score_trend': 'rising'}
    inactive_theme = {'updated_at': fourteen_days_ago, 'discussion_score_trend': 'stable'}

    lifecycle_active = update_theme_lifecycle(active_theme)
    lifecycle_inactive = update_theme_lifecycle(inactive_theme)
    print(f"   - Active theme trend: {lifecycle_active}")
    print(f"   - Inactive theme trend: {lifecycle_inactive}")