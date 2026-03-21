import sqlite3
import os
from datetime import datetime

DB_PATH = "data/opportunities.db"

def get_conn():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # ── Dedup ──────────────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS seen_tweets (
            tweet_id TEXT PRIMARY KEY,
            seen_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Approved / Rejected opportunities log ─────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS opportunities (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            tweet_id         TEXT,
            tweet_text       TEXT,
            tweet_url        TEXT,
            similarity_score REAL,
            eval_decision    TEXT,
            eval_reason      TEXT,
            checker_decision TEXT,
            final_decision   TEXT,
            sent_to_telegram INTEGER DEFAULT 0,
            created_at       TEXT DEFAULT (datetime('now'))
        )
    """)

    # ── Agent performance tracker ─────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS agent_performance (
            agent_id      TEXT PRIMARY KEY,
            approved      INTEGER DEFAULT 0,
            rejected      INTEGER DEFAULT 0,
            false_alarms  INTEGER DEFAULT 0,
            score         REAL    DEFAULT 100.0,
            status        TEXT    DEFAULT 'ALIVE',
            last_updated  TEXT    DEFAULT (datetime('now'))
        )
    """)

    # ── Search phrase tracker ─────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS search_phrases (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            phrase        TEXT UNIQUE,
            source        TEXT DEFAULT 'user',
            success_count INTEGER DEFAULT 0,
            score         REAL    DEFAULT 50.0,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Seed agents
    for agent_id in ["nemotron_evaluator", "groq_checker", "mistral_tiebreaker", "nemotron_inventor"]:
        c.execute("INSERT OR IGNORE INTO agent_performance (agent_id) VALUES (?)", (agent_id,))

    conn.commit()
    conn.close()
    print("[DB] Initialized")


def is_seen(tweet_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM seen_tweets WHERE tweet_id=?", (tweet_id,)).fetchone()
    conn.close()
    return row is not None


def mark_seen(tweet_id: str):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO seen_tweets (tweet_id) VALUES (?)", (tweet_id,))
    conn.commit()
    conn.close()


def save_opportunity(tweet_id, tweet_text, tweet_url, similarity_score,
                     eval_decision, eval_reason, checker_decision, final_decision):
    conn = get_conn()
    conn.execute("""
        INSERT INTO opportunities
            (tweet_id, tweet_text, tweet_url, similarity_score,
             eval_decision, eval_reason, checker_decision, final_decision, sent_to_telegram)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (tweet_id, tweet_text, tweet_url, similarity_score,
          eval_decision, eval_reason, checker_decision, final_decision,
          1 if final_decision == "APPROVE" else 0))
    conn.commit()
    conn.close()


def update_agent(agent_id: str, approved: bool, false_alarm: bool = False):
    from config import AGENT_DEATH_SCORE
    conn = get_conn()
    c = conn.cursor()

    if false_alarm:
        c.execute("UPDATE agent_performance SET false_alarms=false_alarms+1 WHERE agent_id=?", (agent_id,))
    elif approved:
        c.execute("UPDATE agent_performance SET approved=approved+1 WHERE agent_id=?", (agent_id,))
    else:
        c.execute("UPDATE agent_performance SET rejected=rejected+1 WHERE agent_id=?", (agent_id,))

    row = c.execute("SELECT approved, false_alarms, rejected FROM agent_performance WHERE agent_id=?",
                    (agent_id,)).fetchone()
    if row:
        total = row[0] + row[1] + row[2]
        score  = max(0.0, ((row[0] - row[1]) / total) * 100) if total else 100.0
        status = "ALIVE" if score >= AGENT_DEATH_SCORE else "DEAD"
        c.execute("""UPDATE agent_performance
                     SET score=?, status=?, last_updated=datetime('now')
                     WHERE agent_id=?""", (score, status, agent_id))
        if status == "DEAD":
            print(f"[AGENT] ⚠️  {agent_id} has been TURNED OFF (score={score:.1f}%)")

    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = get_conn()
    total_seen     = conn.execute("SELECT COUNT(*) FROM seen_tweets").fetchone()[0]
    total_approved = conn.execute("SELECT COUNT(*) FROM opportunities WHERE final_decision='APPROVE'").fetchone()[0]
    agents = [dict(r) for r in conn.execute(
        "SELECT agent_id, score, status, approved, false_alarms FROM agent_performance"
    ).fetchall()]
    conn.close()
    return {"tweets_seen": total_seen, "opportunities_found": total_approved, "agents": agents}


def get_approved_tweets(limit: int = 20) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT tweet_text FROM opportunities WHERE final_decision='APPROVE' ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_phrases() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT phrase FROM search_phrases ORDER BY score DESC").fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_new_phrase(phrase: str, source: str = "invented"):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO search_phrases (phrase, source) VALUES (?,?)", (phrase, source))
    conn.commit()
    conn.close()
