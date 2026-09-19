-- 运行时库文件：data/memory.sqlite（不进 git）
-- P2-A：facts。P2-B：episodes / style_terms。改表只追加，不改 facts 列。

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    status TEXT NOT NULL DEFAULT 'active',
    source TEXT NOT NULL DEFAULT 'manual',
    evidence TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (category IN ('identity', 'relationship', 'rule', 'preference', 'other')),
    CHECK (status IN ('active', 'pending', 'archived')),
    CHECK (source IN ('user_cmd', 'extract', 'manual', 'group_import'))
);

CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    summary TEXT NOT NULL,
    happened_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_chat_id TEXT NOT NULL DEFAULT 'web:local',
    status TEXT NOT NULL DEFAULT 'pending',
    embedding_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (status IN ('active', 'pending', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status);

CREATE TABLE IF NOT EXISTS style_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL UNIQUE,
    meaning TEXT NOT NULL,
    usage TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'candidate',
    evidence TEXT,
    count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (status IN ('candidate', 'confirmed', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_style_terms_status ON style_terms(status);

-- P2-C：日记、核心印象、相处状态。只追加，不改上面的列。
CREATE TABLE IF NOT EXISTS diaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_diaries_day ON diaries(day);

CREATE TABLE IF NOT EXISTS impressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    source TEXT NOT NULL DEFAULT 'extract',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (status IN ('active', 'pending', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_impressions_status ON impressions(status);

CREATE TABLE IF NOT EXISTS mood_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    energy REAL NOT NULL DEFAULT 0,
    irritation REAL NOT NULL DEFAULT 0,
    affection REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
