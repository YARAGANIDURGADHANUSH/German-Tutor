"""Tiny SQLite memory: learner profile, spaced-repetition vocabulary, event log."""
import json
import os
import sqlite3
import time
from contextlib import contextmanager

DB = os.getenv("DB_PATH", "tutor.db")


@contextmanager
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS learner(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS vocab(
                de TEXT PRIMARY KEY, en TEXT, example TEXT,
                ease REAL DEFAULT 2.5, interval REAL DEFAULT 0,
                reps INTEGER DEFAULT 0, due REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS log(ts REAL, kind TEXT, data TEXT);
            """
        )


def get(key, default=None):
    with db() as c:
        r = c.execute("SELECT v FROM learner WHERE k=?", (key,)).fetchone()
    return json.loads(r["v"]) if r else default


def put(key, value):
    with db() as c:
        c.execute(
            "INSERT INTO learner(k,v) VALUES(?,?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def log(kind, data):
    with db() as c:
        c.execute(
            "INSERT INTO log VALUES(?,?,?)",
            (time.time(), kind, json.dumps(data, ensure_ascii=False)),
        )


def add_vocab(items):
    n = 0
    with db() as c:
        for it in items:
            de, en = (it.get("de") or "").strip(), (it.get("en") or "").strip()
            if not de or not en:
                continue
            cur = c.execute(
                "INSERT OR IGNORE INTO vocab(de,en,example,due) VALUES(?,?,?,?)",
                (de, en, it.get("example", ""), time.time() + 600),
            )
            n += cur.rowcount
    return n


def due_vocab(n=5):
    with db() as c:
        rows = c.execute(
            "SELECT de,en,example FROM vocab WHERE due<=? ORDER BY due LIMIT ?",
            (time.time(), n),
        ).fetchall()
    return [dict(r) for r in rows]


def review(de, quality):
    """SM-2 spaced repetition. quality: 0 (blackout) .. 5 (perfect)."""
    quality = max(0, min(5, int(quality)))
    with db() as c:
        r = c.execute("SELECT * FROM vocab WHERE de=?", (de,)).fetchone()
        if not r:
            return False
        ease, interval, reps = r["ease"], r["interval"], r["reps"]
        if quality < 3:
            reps, interval = 0, 0.007  # retry in ~10 minutes
        else:
            reps += 1
            interval = 1 if reps == 1 else 3 if reps == 2 else interval * ease
        ease = max(1.3, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        c.execute(
            "UPDATE vocab SET ease=?, interval=?, reps=?, due=? WHERE de=?",
            (ease, interval, reps, time.time() + interval * 86400, de),
        )
    return True


def stats():
    now = time.time()
    with db() as c:
        total = c.execute("SELECT COUNT(*) n FROM vocab").fetchone()["n"]
        due = c.execute("SELECT COUNT(*) n FROM vocab WHERE due<=?", (now,)).fetchone()["n"]
        recent = [
            dict(r)
            for r in c.execute("SELECT de,en FROM vocab ORDER BY rowid DESC LIMIT 8")
        ]
    return {
        "level": get("level", "A1"),
        "unit": get("unit", 0),
        "vocab_total": total,
        "due": due,
        "recent": recent,
        "strengths": get("strengths", []),
        "weaknesses": get("weaknesses", []),
        "exams": get("exams", [])[-3:],
    }
