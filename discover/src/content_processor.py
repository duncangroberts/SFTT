#!/usr/bin/env python
"""Processes content from story URLs."""

import requests
from bs4 import BeautifulSoup

def fetch_and_extract_text(url):
    """Fetches a URL and extracts the main text content."""
    if not url:
        return ""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Check for content type to avoid parsing non-textual content
        if 'text/html' not in response.headers.get('Content-Type', ''):
            print(f"Skipping non-html content at {url}")
            return ""

        soup = BeautifulSoup(response.content, 'lxml')

        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        # Get text and clean it up
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)

        return text
    except requests.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        return ""
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return ""

if __name__ == '__main__':
    # Example usage
    test_url = "https://www.theverge.com/2023/10/26/23933453/google-meta-q3-2023-earnings-ai-spending-reality-labs-losses"
    print(f"Fetching content from: {test_url}")
    content = fetch_and_extract_text(test_url)
    print(content[:1000] + "...")