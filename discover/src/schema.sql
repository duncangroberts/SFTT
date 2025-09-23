-- Database schema for the Discover module

-- Themes table to store aggregated data about discussion themes
CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    discussion_score INTEGER DEFAULT 0,
    sentiment_score REAL DEFAULT 0.0,
    discussion_score_trend TEXT DEFAULT 'stable',
    sentiment_score_trend TEXT DEFAULT 'stable',
    embedding BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stories table to track processed Hacker News stories
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to update the updated_at timestamp on themes table
CREATE TRIGGER IF NOT EXISTS update_themes_updated_at
AFTER UPDATE ON themes
FOR EACH ROW
BEGIN
    UPDATE themes SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

-- Association table for the many-to-many relationship between themes and stories
CREATE TABLE IF NOT EXISTS theme_stories (
    theme_id INTEGER NOT NULL,
    story_id INTEGER NOT NULL,
    FOREIGN KEY (theme_id) REFERENCES themes(id),
    FOREIGN KEY (story_id) REFERENCES stories(id),
    PRIMARY KEY (theme_id, story_id)
);
;
