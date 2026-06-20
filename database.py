import sqlite3
import os

DB_PATH = "data.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS creators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            name TEXT NOT NULL,
            tiktok TEXT,
            youtube TEXT,
            instagram TEXT,
            instagram_verified INTEGER DEFAULT 0,
            joined_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            views INTEGER DEFAULT 0,
            last_checked TEXT,
            added_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (creator_id) REFERENCES creators(id)
        );
    """)
    conn.commit()
    conn.close()

def get_creator(tg_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM creators WHERE tg_id=?", (tg_id,)).fetchone()
    conn.close()
    return row

def create_creator(tg_id, username, name, tiktok, youtube, instagram):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO creators (tg_id, username, name, tiktok, youtube, instagram) VALUES (?,?,?,?,?,?)",
        (tg_id, username, name, tiktok, youtube, instagram)
    )
    conn.commit()
    conn.close()

def get_all_creators():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM creators ORDER BY joined_at DESC").fetchall()
    conn.close()
    return rows

def add_video_db(creator_id, platform, url, title, views):
    conn = get_conn()
    conn.execute(
        "INSERT INTO videos (creator_id, platform, url, title, views, last_checked) VALUES (?,?,?,?,?,datetime('now'))",
        (creator_id, platform, url, title, views)
    )
    conn.commit()
    conn.close()

def get_videos_by_creator(creator_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM videos WHERE creator_id=? ORDER BY added_at DESC", (creator_id,)).fetchall()
    conn.close()
    return rows

def update_video_views(video_id, views):
    conn = get_conn()
    conn.execute("UPDATE videos SET views=?, last_checked=datetime('now') WHERE id=?", (views, video_id))
    conn.commit()
    conn.close()

def get_all_videos():
    conn = get_conn()
    rows = conn.execute("SELECT v.*, c.name as creator_name FROM videos v JOIN creators c ON v.creator_id=c.id").fetchall()
    conn.close()
    return rows

def verify_instagram(creator_id):
    conn = get_conn()
    conn.execute("UPDATE creators SET instagram_verified=1 WHERE id=?", (creator_id,))
    conn.commit()
    conn.close()

def add_manual_views(video_id, views):
    conn = get_conn()
    conn.execute("UPDATE videos SET views=?, last_checked=datetime('now') WHERE id=?", (views, video_id))
    conn.commit()
    conn.close()
