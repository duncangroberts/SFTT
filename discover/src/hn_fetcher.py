#!/usr/bin/env python
"""Fetches stories and comments from Hacker News."""

import requests
import datetime
from concurrent.futures import ThreadPoolExecutor

HN_API_BASE_URL = "https://hacker-news.firebaseio.com/v0"

def get_story_details(story_id):
    """Fetches details for a single story."""
    try:
        response = requests.get(f"{HN_API_BASE_URL}/item/{story_id}.json")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching story {story_id}: {e}")
        return None

def get_top_stories(limit=500):
    """Fetches the top stories from Hacker News."""
    try:
        response = requests.get(f"{HN_API_BASE_URL}/topstories.json")
        response.raise_for_status()
        story_ids = response.json()
        return story_ids[:limit]
    except requests.RequestException as e:
        print(f"Error fetching top stories: {e}")
        return []

def get_comments(comment_ids):
    """Fetches comments in parallel."""
    comments = []
    if not comment_ids:
        return comments

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_comment_id = {executor.submit(get_story_details, comment_id): comment_id for comment_id in comment_ids}
        for future in future_to_comment_id:
            comment = future.result()
            if comment and not comment.get('deleted') and not comment.get('dead') and comment.get('text'):
                comments.append(comment)
    return comments

def fetch_stories_for_past_days(days=30, score_threshold=100, comments_threshold=50):
    """Fetches stories from the past N days that meet score and comment thresholds."""
    print(f"Fetching stories from the past {days} days...")
    top_story_ids = get_top_stories()
    stories = []
    
    one_month_ago_timestamp = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_story_id = {executor.submit(get_story_details, story_id): story_id for story_id in top_story_ids}
        for future in future_to_story_id:
            story = future.result()
            if story:
                if story.get('time', 0) > one_month_ago_timestamp and \
                   story.get('score', 0) >= score_threshold and \
                   story.get('descendants', 0) >= comments_threshold:
                    stories.append(story)
    
    print(f"Found {len(stories)} stories meeting the criteria.")
    return stories

if __name__ == '__main__':
    # Example usage: fetch and print top stories from the last month with high engagement
    highly_discussed_stories = fetch_stories_for_past_days(days=30)
    for story in highly_discussed_stories:
        print(f"- {story.get('title')} (Score: {story.get('score')}, Comments: {story.get('descendants')})")