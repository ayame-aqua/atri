-- P2-A 事实表。P1 只预置文件，不创建库、不接线。
-- 运行时库文件：data/memory.sqlite（不进 git）

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
