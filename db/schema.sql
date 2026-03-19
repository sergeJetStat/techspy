CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT UNIQUE NOT NULL,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_crawled TEXT,
    crawl_tier INTEGER NOT NULL DEFAULT 3,
    status TEXT NOT NULL DEFAULT 'pending',
    last_status_code INTEGER
);

CREATE TABLE IF NOT EXISTS technologies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    category TEXT NOT NULL,
    website TEXT,
    is_custom INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS site_technologies (
    site_id INTEGER NOT NULL REFERENCES sites(id),
    tech_id INTEGER NOT NULL REFERENCES technologies(id),
    confidence INTEGER NOT NULL,
    version TEXT,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (site_id, tech_id)
);

CREATE TABLE IF NOT EXISTS tech_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL REFERENCES sites(id),
    tech_id INTEGER NOT NULL REFERENCES technologies(id),
    change_type TEXT NOT NULL CHECK (change_type IN ('added', 'removed', 'version_change')),
    old_version TEXT,
    new_version TEXT,
    detected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'error')),
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS unknown_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type TEXT NOT NULL,
    signal_value TEXT NOT NULL,
    domain TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed INTEGER NOT NULL DEFAULT 0,
    UNIQUE (signal_type, signal_value)
);

CREATE INDEX IF NOT EXISTS idx_sites_domain ON sites(domain);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs(status, priority DESC);
CREATE INDEX IF NOT EXISTS idx_unknown_signals_processed ON unknown_signals(processed, count DESC);
