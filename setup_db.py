import sqlite3

DB_PATH = "twitter_accounts.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Table to store connected Twitter accounts
cursor.execute('''
CREATE TABLE IF NOT EXISTS twitter_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    twitter_id TEXT UNIQUE,
    twitter_handle TEXT,
    access_token TEXT,
    refresh_token TEXT,
    token_expiry DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    service_enabled INTEGER DEFAULT 0
)
''')

# Table to store global settings (like tweet_id)
cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
''')

# Initialize default setting if not exists
cursor.execute(
    "INSERT OR IGNORE INTO settings (key, value) VALUES ('tweet_id', '')")

conn.commit()
conn.close()
print("✅ Database setup completed.")
