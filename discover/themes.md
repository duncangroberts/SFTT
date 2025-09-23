# Current Theme Determination Logic

This document details the current logic used by the Discover module to generate themes from Hacker News stories.

---

### 1. The Logic

The theme for each story is determined by the `extract_theme_from_text` function in the `discover/src/analysis.py` file. Here is a step-by-step breakdown of what it does:

1.  **Combine Text:** It receives the full text of a story, which is a combination of the **story's title**, the **full content of the linked article**, and the **full text of all comments**.

2.  **Truncate for Size:** It truncates this combined text to the first 8,000 characters to ensure it fits within the language model's context window.

3.  **Call the LLM:** It sends this truncated text to the LLM using the system prompt below and asks for a theme. It uses very specific generation settings to get a short, low-entropy response:
    -   `temperature`: 0.25
    -   `top_p`: 0.9
    -   `top_k`: 40
    -   `repeat_penalty`: 1.1
    -   `max_tokens`: 12
    -   `stop`: The model is instructed to stop generating at the first newline.

4.  **Clean Up:** It takes the LLM's response, strips any leading/trailing whitespace, and removes any stray quotation marks or periods.

5.  **Return Theme:** The cleaned-up text is then returned as the final theme name. If the LLM returns an empty string, it defaults to "Uncategorized".


---

### 2. The System Prompt

This is the exact system prompt that is sent to the language model for every theme extraction request:

```
You label tech discussion with durable, mid-level themes.
Rules: Output a 2-5 word NOUN PHRASE that could apply to many similar posts.
Do not include company names, product names, versions, dates, or one-off events.
Return only the theme, one line, no punctuation.
```

---

### 3. The Code

For full transparency, here is the complete Python function from `discover/src/analysis.py` that implements this logic:

```python
def extract_theme_from_text(text_content):
    """Extracts a theme using a detailed prompt."""
    if not text_content:
        return "Uncategorized"

    max_length = 8000
    truncated_content = text_content[:max_length]

    system_prompt = (
        "You label tech discussion with durable, mid-level themes.\n"
        "Rules: Output a 2-5 word NOUN PHRASE that could apply to many similar posts.\n"
        "Do not include company names, product names, versions, dates, or one-off events.\n"
        "Return only the theme, one line, no punctuation."
    )

    prompt = f"{truncated_content}"

    try:
        theme = generate_completion(
            prompt,
            system_prompt=system_prompt,
            temperature=0.25,
            top_p=0.9,
            top_k=40,
            repeat_penalty=1.1,
            max_tokens=12,
            stop=['\\n']
        )
        theme = theme.strip().replace('"', '').replace('.', '')
        return theme if theme else "Uncategorized"
            
    except Exception as e:
        print(f"Error during theme extraction: {e}")
        return "Uncategorized"
```