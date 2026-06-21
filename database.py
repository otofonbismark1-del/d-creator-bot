import sqlite3

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
            views_at_period_start INTEGER DEFAULT 0,
            pending_views INTEGER DEFAULT NULL,
            last_checked TEXT,
            period_id INTEGER,
            added_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (creator_id) REFERENCES creators(id)
        );

        CREATE TABLE IF NOT EXISTS periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            closed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS creator_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            period_id INTEGER NOT NULL,
            rate_type TEXT NOT NULL DEFAULT 'per_1000',
            rate_value REAL NOT NULL DEFAULT 60,
            rate_fix REAL DEFAULT 0,
            UNIQUE(creator_id, period_id),
            FOREIGN KEY (creator_id) REFERENCES creators(id),
            FOREIGN KEY (period_id) REFERENCES periods(id)
        );

        CREATE TABLE IF NOT EXISTS payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id INTEGER NOT NULL,
            period_id INTEGER NOT NULL,
            views_gained INTEGER DEFAULT 0,
            video_count INTEGER DEFAULT 0,
            amount REAL DEFAULT 0,
            paid_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (creator_id) REFERENCES creators(id),
            FOREIGN KEY (period_id) REFERENCES periods(id)
        );
    """)
    row = conn.execute("SELECT id FROM periods WHERE closed=0 ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        _create_new_period(conn)
    conn.commit()
    conn.close()

def _create_new_period(conn):
    from datetime import date
    import calendar
    today = date.today()
    if today.day <= 15:
        start = date(today.year, today.month, 1)
        end = date(today.year, today.month, 15)
    else:
        last_day = calendar.monthrange(today.year, today.month)[1]
        start = date(today.year, today.month, 16)
        end = date(today.year, today.month, last_day)
    conn.execute("INSERT INTO periods (start_date, end_date) VALUES (?,?)", (str(start), str(end)))

def get_current_period():
    conn = get_conn()
    row = conn.execute("SELECT * FROM periods WHERE closed=0 ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row

def get_all_periods():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM periods ORDER BY id DESC").fetchall()
    conn.close()
    return rows

def get_period_by_id(period_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM periods WHERE id=?", (period_id,)).fetchone()
    conn.close()
    return row

def get_creator_rate(creator_id, period_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM creator_rates WHERE creator_id=? AND period_id=?",
        (creator_id, period_id)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"rate_type": "per_1000", "rate_value": 60, "rate_fix": 0}

def set_creator_rate(creator_id, period_id, rate_type, rate_value, rate_fix=0):
    conn = get_conn()
    conn.execute(
        """INSERT INTO creator_rates (creator_id, period_id, rate_type, rate_value, rate_fix)
           VALUES (?,?,?,?,?)
           ON CONFLICT(creator_id, period_id) DO UPDATE SET rate_type=excluded.rate_type,
           rate_value=excluded.rate_value, rate_fix=excluded.rate_fix""",
        (creator_id, period_id, rate_type, rate_value, rate_fix)
    )
    conn.commit()
    conn.close()

def calc_payout(views_gained, video_count, rate):
    if rate["rate_type"] == "per_1000":
        return round(views_gained / 1000 * rate["rate_value"], 2)
    return round(video_count * rate["rate_fix"] + views_gained / 1000 * rate["rate_value"], 2)

def close_period_and_create_next(period_id):
    conn = get_conn()
    period = conn.execute("SELECT * FROM periods WHERE id=?", (period_id,)).fetchone()
    if not period:
        conn.close()
        return None, []

    videos = conn.execute(
        "SELECT v.*, c.id as cid, c.name as cname FROM videos v JOIN creators c ON v.creator_id=c.id WHERE v.period_id=?",
        (period_id,)
    ).fetchall()

    creator_data = {}
    for v in videos:
        cid = v["cid"]
        gained = max(0, v["views"] - v["views_at_period_start"])
        if cid not in creator_data:
            creator_data[cid] = {"views": 0, "video_count": 0, "name": v["cname"], "videos": []}
        creator_data[cid]["views"] += gained
        creator_data[cid]["video_count"] += 1
        creator_data[cid]["videos"].append(dict(v))

    payout_summary = []
    for cid, data in creator_data.items():
        rate = get_creator_rate(cid, period_id)
        amount = calc_payout(data["views"], data["video_count"], rate)
        conn.execute(
            "INSERT INTO payouts (creator_id, period_id, views_gained, video_count, amount) VALUES (?,?,?,?,?)",
            (cid, period_id, data["views"], data["video_count"], amount)
        )
        payout_summary.append({"creator_id": cid, "name": data["name"], "views": data["views"],
                                "video_count": data["video_count"], "amount": amount, "videos": data["videos"]})

    conn.execute("UPDATE periods SET closed=1 WHERE id=?", (period_id,))
    _create_new_period(conn)
    new_period = conn.execute("SELECT id FROM periods WHERE closed=0 ORDER BY id DESC LIMIT 1").fetchone()
    conn.execute("UPDATE videos SET period_id=?, views_at_period_start=views", (new_period["id"],))
    conn.commit()
    conn.close()
    return new_period["id"], payout_summary

def get_payouts_by_creator(creator_id):
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.*, pr.start_date, pr.end_date FROM payouts p
           JOIN periods pr ON p.period_id=pr.id
           WHERE p.creator_id=? ORDER BY p.paid_at DESC""",
        (creator_id,)
    ).fetchall()
    conn.close()
    return rows

def get_all_payouts():
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.*, c.name as creator_name, pr.start_date, pr.end_date
           FROM payouts p JOIN creators c ON p.creator_id=c.id JOIN periods pr ON p.period_id=pr.id
           ORDER BY p.paid_at DESC"""
    ).fetchall()
    conn.close()
    return rows

def get_creator(tg_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM creators WHERE tg_id=?", (tg_id,)).fetchone()
    conn.close()
    return row

def get_creator_by_id(cid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM creators WHERE id=?", (cid,)).fetchone()
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
    period = conn.execute("SELECT id FROM periods WHERE closed=0 ORDER BY id DESC LIMIT 1").fetchone()
    period_id = period["id"] if period else None
    conn.execute(
        """INSERT INTO videos (creator_id, platform, url, title, views, views_at_period_start, last_checked, period_id)
           VALUES (?,?,?,?,?,?,datetime('now'),?)""",
        (creator_id, platform, url, title, views, views, period_id)
    )
    conn.commit()
    conn.close()

def get_videos_by_creator(creator_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM videos WHERE creator_id=? ORDER BY added_at DESC", (creator_id,)).fetchall()
    conn.close()
    return rows

def get_video_by_id(video_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    conn.close()
    return row

def delete_video(video_id, creator_id):
    conn = get_conn()
    conn.execute("DELETE FROM videos WHERE id=? AND creator_id=?", (video_id, creator_id))
    conn.commit()
    conn.close()

def update_video_views(video_id, views):
    conn = get_conn()
    conn.execute("UPDATE videos SET views=?, last_checked=datetime('now') WHERE id=?", (views, video_id))
    conn.commit()
    conn.close()

def set_pending_views(video_id, views):
    conn = get_conn()
    conn.execute("UPDATE videos SET pending_views=? WHERE id=?", (views, video_id))
    conn.commit()
    conn.close()

def approve_pending_views(video_id):
    conn = get_conn()
    conn.execute(
        "UPDATE videos SET views=pending_views, pending_views=NULL, last_checked=datetime('now') WHERE id=? AND pending_views IS NOT NULL",
        (video_id,)
    )
    conn.commit()
    conn.close()

def get_all_videos():
    conn = get_conn()
    rows = conn.execute(
        "SELECT v.*, c.name as creator_name, c.tg_id as creator_tg_id FROM videos v JOIN creators c ON v.creator_id=c.id"
    ).fetchall()
    conn.close()
    return rows

def get_pending_instagram_videos():
    conn = get_conn()
    rows = conn.execute(
        """SELECT v.*, c.name as creator_name, c.tg_id as creator_tg_id
           FROM videos v JOIN creators c ON v.creator_id=c.id
           WHERE v.platform='instagram' AND v.pending_views IS NOT NULL"""
    ).fetchall()
    conn.close()
    return rows
