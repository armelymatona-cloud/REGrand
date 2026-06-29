import sqlite3
import logging
import os
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._connect()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                phone TEXT PRIMARY KEY,
                session_string TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                proxy TEXT PRIMARY KEY,
                protocol TEXT DEFAULT 'http',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                target TEXT PRIMARY KEY,
                reports INTEGER DEFAULT 1,
                last_reported TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()
        logger.info("✅ Base de données initialisée")

    # ---- Accounts ----
    def get_active_accounts(self):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT phone, session_string FROM accounts WHERE active = 1")
        rows = cur.fetchall()
        conn.close()
        return [Account(phone=r[0], session_string=r[1]) for r in rows]

    def update_account_status(self, phone: str, active: bool):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("UPDATE accounts SET active = ? WHERE phone = ?", (int(active), phone))
        conn.commit()
        conn.close()

    # ---- Proxies ----
    def get_proxy_count(self) -> int:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM proxies")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else 0

    def add_proxies(self, proxies: list) -> int:
        conn = self._connect()
        cur = conn.cursor()
        new_count = 0
        for proxy in proxies:
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO proxies (proxy) VALUES (?)",
                    (proxy,)
                )
                if cur.rowcount > 0:
                    new_count += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        return new_count

    def get_random_proxies(self, limit: int = 5) -> list:
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT proxy FROM proxies ORDER BY RANDOM() LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        conn.close()
        return [row[0] for row in rows]

    # ---- Targets ----
    def add_target(self, target: str):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO targets (target) VALUES (?)
        """, (target,))
        conn.commit()
        conn.close()

    def increment_target_reports(self, target: str):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "UPDATE targets SET reports = reports + 1, last_reported = datetime('now') WHERE target = ?",
            (target,)
        )
        conn.commit()
        conn.close()


class Account:
    def __init__(self, phone: str, session_string: str):
        self.phone = phone
        self.session_string = session_string
