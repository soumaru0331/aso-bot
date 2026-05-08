CREATE TABLE IF NOT EXISTS recruitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message_id TEXT,
    creator_id TEXT NOT NULL,
    game TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    max_players INTEGER NOT NULL DEFAULT 0,
    required_role_name TEXT,
    cancel_deadline_minutes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recruitment_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    join_type TEXT NOT NULL,
    reason TEXT,
    available_until TEXT,
    joined_at TEXT NOT NULL,
    UNIQUE(recruitment_id, user_id),
    FOREIGN KEY(recruitment_id) REFERENCES recruitments(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recruitment_id INTEGER NOT NULL,
    minutes_before INTEGER NOT NULL,
    sent INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(recruitment_id) REFERENCES recruitments(id)
);
