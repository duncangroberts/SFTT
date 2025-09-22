DROP VIEW IF EXISTS v_items;
CREATE VIEW v_items AS
SELECT 'hn' AS source,
       'story' AS obj_type,
       CAST(s.id AS TEXT) AS obj_id,
       s.title AS title_or_name,
       COALESCE(s.domain, 'news.ycombinator.com') AS domain,
       s.time AS ts_unix,
       COALESCE(s.score, 0) AS metric_1,
       COALESCE(s.descendants, 0) AS metric_2,
       e.vector
FROM stories s
LEFT JOIN embeddings e ON e.obj_id = CAST(s.id AS TEXT);

CREATE VIEW IF NOT EXISTS v_story_daily_signal AS
SELECT s.id,
       DATE(s.time, 'unixepoch') AS day,
       COALESCE(s.score, 0) AS score,
       COALESCE(s.descendants, 0) AS comment_count
FROM stories s;

CREATE VIEW IF NOT EXISTS v_trend_snapshots AS
SELECT ts.snapshot_id,
       ts.trend_id,
       tc.fingerprint,
       tc.canonical_label,
       tc.canonical_terms,
       ts.window_start,
       ts.window_end,
       ts.story_count,
       ts.comment_count,
       ts.signal,
       ts.delta,
       ts.novelty,
       ts.persistence,
       tc.first_seen,
       tc.last_seen,
       tc.times_seen,
       tc.latest_signal,
       tc.latest_delta,
       tc.latest_story_count,
       tc.latest_comment_count,
       tc.novelty AS cluster_novelty,
       tc.persistence AS cluster_persistence,
       tc.active
FROM trend_snapshots ts
JOIN trend_clusters tc ON tc.trend_id = ts.trend_id;

CREATE VIEW IF NOT EXISTS v_trend_signal_history AS
SELECT ts.trend_id,
       tc.canonical_label,
       ts.window_end AS period_end,
       ts.signal
FROM trend_snapshots ts
JOIN trend_clusters tc ON tc.trend_id = ts.trend_id;

CREATE VIEW IF NOT EXISTS v_hot_terms AS
SELECT surge_id,
       run_id,
       term,
       current_score,
       baseline_score,
       surge_ratio,
       surge_delta,
       created_at
FROM term_surge_snapshots;
