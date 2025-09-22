PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT,
    domain TEXT,
    by TEXT,
    time INTEGER NOT NULL,
    score INTEGER,
    descendants INTEGER,
    fetched_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    parent INTEGER NOT NULL,
    by TEXT,
    time INTEGER NOT NULL,
    text TEXT,
    story_id INTEGER NOT NULL,
    FOREIGN KEY(story_id) REFERENCES stories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS embeddings (
    obj_type TEXT NOT NULL,
    obj_id TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL,
    PRIMARY KEY(obj_type, obj_id)
);

CREATE TABLE IF NOT EXISTS embedding_meta (
    obj_type TEXT NOT NULL,
    obj_id TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(obj_type, obj_id)
);

CREATE TABLE IF NOT EXISTS terms (
    term TEXT NOT NULL,
    obj_type TEXT NOT NULL,
    obj_id TEXT NOT NULL,
    weight REAL NOT NULL,
    PRIMARY KEY(term, obj_type, obj_id)
);

CREATE TABLE IF NOT EXISTS trend_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_id INTEGER,
    run_id INTEGER,
    signal REAL,
    sentiment REAL,
    FOREIGN KEY(trend_id) REFERENCES trend_clusters(trend_id),
    FOREIGN KEY(run_id) REFERENCES run_logs(id)
);

CREATE TABLE IF NOT EXISTS trend_clusters (
    trend_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT UNIQUE,
    canonical_label TEXT,
    llm_summary TEXT,
    canonical_terms TEXT,
    first_seen TEXT,
    last_seen TEXT,
    times_seen INTEGER DEFAULT 1,
    latest_signal REAL,
    latest_delta REAL,
    latest_story_count INTEGER,
    latest_comment_count INTEGER,
    latest_sentiment REAL,
    novelty REAL,
    persistence REAL,
    centroid BLOB,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trend_cluster_members (
    trend_id INTEGER NOT NULL,
    obj_type TEXT NOT NULL,
    obj_id TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY(trend_id, obj_type, obj_id),
    FOREIGN KEY(trend_id) REFERENCES trend_clusters(trend_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trend_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    story_count INTEGER NOT NULL,
    comment_count INTEGER NOT NULL DEFAULT 0,
    signal REAL NOT NULL,
    delta REAL NOT NULL,
    novelty REAL NOT NULL,
    persistence REAL NOT NULL,
    FOREIGN KEY(trend_id) REFERENCES trend_clusters(trend_id) ON DELETE CASCADE,
    FOREIGN KEY(run_id) REFERENCES run_logs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS term_surge_snapshots (
    surge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    term TEXT NOT NULL,
    current_score REAL NOT NULL,
    baseline_score REAL NOT NULL,
    surge_ratio REAL NOT NULL,
    surge_delta REAL NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, term),
    FOREIGN KEY(run_id) REFERENCES run_logs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    since_arg TEXT,
    embed_model TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS run_stage_logs (
    stage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    duration REAL,
    detail TEXT,
    FOREIGN KEY(run_id) REFERENCES run_logs(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_state (
    source TEXT PRIMARY KEY,
    cursor TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stories_time ON stories(time DESC);
CREATE INDEX IF NOT EXISTS idx_comments_story ON comments(story_id);
CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term);
CREATE INDEX IF NOT EXISTS idx_terms_obj ON terms(obj_type, obj_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_obj ON embeddings(obj_type, obj_id);
CREATE INDEX IF NOT EXISTS idx_trend_snapshots_trend ON trend_snapshots(trend_id);
CREATE INDEX IF NOT EXISTS idx_trend_snapshots_run ON trend_snapshots(run_id);
CREATE INDEX IF NOT EXISTS idx_trend_cluster_members_obj ON trend_cluster_members(obj_type, obj_id);
CREATE INDEX IF NOT EXISTS idx_run_stage_logs_run ON run_stage_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_term_surge_run ON term_surge_snapshots(run_id, surge_ratio);
