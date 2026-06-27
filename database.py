import sqlite3
import json
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path="bot.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
    
    def _init_tables(self):
        cursor = self.conn.cursor()
        
        # Table des comptes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                phone TEXT PRIMARY KEY,
                api_id INTEGER,
                api_hash TEXT,
                session_string TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                is_banned INTEGER DEFAULT 0,
                ban_reason TEXT
            )
        """)
        
        # Table des sessions backup
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions_backup (
                phone TEXT PRIMARY KEY,
                session_string TEXT,
                device_model TEXT,
                system_version TEXT,
                app_version TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (phone) REFERENCES accounts(phone) ON DELETE CASCADE
            )
        """)
        
        # Table des pending logins (persistante)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_logins (
                user_id INTEGER,
                phone TEXT PRIMARY KEY,
                api_id INTEGER,
                api_hash TEXT,
                phone_code_hash TEXT,
                status TEXT DEFAULT 'code_sent',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        
        # Table des proxies
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                protocol TEXT DEFAULT 'socks5',
                username TEXT,
                password TEXT,
                country TEXT,
                anonymity TEXT,
                is_valid INTEGER DEFAULT 0,
                last_checked TIMESTAMP,
                response_time_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ip, port, protocol)
            )
        """)
        
        # Table des cibles
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                username TEXT PRIMARY KEY,
                report_count INTEGER DEFAULT 0,
                last_reported TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table des logs de report
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS report_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT,
                account_phone TEXT,
                status TEXT,
                error_message TEXT,
                response_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
        logger.info("✅ Tables initialisées")
    
    # ========== COMPTES ==========
    
    def add_account(self, phone, api_id, api_hash):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO accounts (phone, api_id, api_hash, status)
            VALUES (?, ?, ?, 'pending')
        """, (phone, api_id, api_hash))
        self.conn.commit()
        logger.debug(f"Compte ajouté: {phone}")
    
    def remove_account(self, phone):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM accounts WHERE phone = ?", (phone,))
        cursor.execute("DELETE FROM sessions_backup WHERE phone = ?", (phone,))
        self.conn.commit()
        logger.info(f"Compte supprimé: {phone}")
    
    def update_account_session(self, phone, session_string):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE accounts SET session_string = ?, last_used = CURRENT_TIMESTAMP
            WHERE phone = ?
        """, (session_string, phone))
        # Backup dans la table sessions_backup
        cursor.execute("""
            INSERT OR REPLACE INTO sessions_backup (phone, session_string, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (phone, session_string))
        self.conn.commit()
        logger.debug(f"Session sauvegardée pour {phone}")
    
    def update_account_status(self, phone, status):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE accounts SET status = ? WHERE phone = ?", (status, phone))
        self.conn.commit()
    
    def get_account_session(self, phone):
        cursor = self.conn.cursor()
        cursor.execute("SELECT session_string FROM accounts WHERE phone = ?", (phone,))
        row = cursor.fetchone()
        if row and row['session_string']:
            return row['session_string']
        # Fallback sur sessions_backup
        cursor.execute("SELECT session_string FROM sessions_backup WHERE phone = ?", (phone,))
        row = cursor.fetchone()
        return row['session_string'] if row else None
    
    def get_all_accounts(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM accounts ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_active_accounts(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE status = 'active' AND is_banned = 0 ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    
    def get_account_count(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM accounts")
        return cursor.fetchone()['count']
    
    def get_active_account_count(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM accounts WHERE status = 'active' AND is_banned = 0")
        return cursor.fetchone()['count']
    
    def ban_account(self, phone, reason=""):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE accounts SET is_banned = 1, ban_reason = ?, status = 'banned'
            WHERE phone = ?
        """, (reason, phone))
        self.conn.commit()
        logger.warning(f"Compte banni: {phone} - {reason}")
    
    # ========== PENDING LOGINS ==========
    
    def set_pending_login(self, user_id, phone, api_id, api_hash, status="code_sent", phone_code_hash=""):
        cursor = self.conn.cursor()
        # Expire dans 5 minutes
        expires_at = datetime.now().timestamp() + 300
        cursor.execute("""
            INSERT OR REPLACE INTO pending_logins (user_id, phone, api_id, api_hash, phone_code_hash, status, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, phone, api_id, api_hash, phone_code_hash, status, expires_at))
        self.conn.commit()
        logger.debug(f"Pending login sauvegardé: {phone}")
    
    def get_pending_login(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM pending_logins 
            WHERE user_id = ? AND expires_at > ?
            ORDER BY created_at DESC LIMIT 1
        """, (user_id, datetime.now().timestamp()))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_all_pending(self):
        """Récupère tous les pending logins non expirés"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM pending_logins 
            WHERE expires_at > ?
            ORDER BY created_at DESC
        """, (datetime.now().timestamp(),))
        return [dict(row) for row in cursor.fetchall()]
    
    def remove_pending_login(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM pending_logins WHERE user_id = ?", (user_id,))
        self.conn.commit()
        logger.debug(f"Pending login supprimé pour user {user_id}")
    
    def cleanup_expired_pending(self):
        """Nettoie les pending logins expirés"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM pending_logins WHERE expires_at < ?", (datetime.now().timestamp(),))
        deleted = cursor.rowcount
        if deleted:
            self.conn.commit()
            logger.info(f"Nettoyage: {deleted} pending expirés supprimés")
        return deleted
    
    # ========== PROXIES ==========
    
    def add_proxy(self, ip, port, protocol="socks5", username=None, password=None, country=None, anonymity=None):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO proxies (ip, port, protocol, username, password, country, anonymity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ip, port, protocol, username, password, country, anonymity))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur ajout proxy {ip}:{port}: {e}")
            return False
    
    def add_proxies_batch(self, proxies_list):
        """Ajoute une liste de proxies en batch"""
        if not proxies_list:
            return 0
        cursor = self.conn.cursor()
        added = 0
        for p in proxies_list:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO proxies (ip, port, protocol, username, password, country, anonymity)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    p.get('ip', p.get('host')),
                    p.get('port', 1080),
                    p.get('protocol', 'socks5'),
                    p.get('username'),
                    p.get('password'),
                    p.get('country'),
                    p.get('anonymity')
                ))
                if cursor.rowcount > 0:
                    added += 1
            except Exception as e:
                logger.debug(f"Erreur batch proxy: {e}")
                continue
        self.conn.commit()
        logger.info(f"Batch: {added} proxies ajoutés")
        return added
    
    def get_proxy_count(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM proxies")
        return cursor.fetchone()['count']
    
    def get_valid_proxy_count(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM proxies WHERE is_valid = 1")
        return cursor.fetchone()['count']
    
    def get_proxies(self, limit=100, only_valid=True):
        cursor = self.conn.cursor()
        if only_valid:
            cursor.execute("""
                SELECT * FROM proxies WHERE is_valid = 1 
                ORDER BY response_time_ms ASC NULLS LAST, created_at DESC 
                LIMIT ?
            """, (limit,))
        else:
            cursor.execute("""
                SELECT * FROM proxies ORDER BY created_at DESC LIMIT ?
            """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_random_proxy(self):
        """Récupère un proxy valide aléatoire"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM proxies WHERE is_valid = 1 
            ORDER BY RANDOM() LIMIT 1
        """)
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def update_proxy_validity(self, proxy_id, is_valid, response_time_ms=None):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE proxies SET is_valid = ?, last_checked = CURRENT_TIMESTAMP, 
            response_time_ms = ? WHERE id = ?
        """, (1 if is_valid else 0, response_time_ms, proxy_id))
        self.conn.commit()
    
    def mark_proxy_invalid(self, ip, port):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE proxies SET is_valid = 0, last_checked = CURRENT_TIMESTAMP 
            WHERE ip = ? AND port = ?
        """, (ip, port))
        self.conn.commit()
    
    def clear_invalid_proxies(self):
        """Supprime les proxies invalides"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM proxies WHERE is_valid = 0")
        deleted = cursor.rowcount
        if deleted:
            self.conn.commit()
            logger.info(f"Nettoyage: {deleted} proxies invalides supprimés")
        return deleted
    
    def get_proxy_stats(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN is_valid = 1 THEN 1 ELSE 0 END) as valid,
                SUM(CASE WHEN is_valid = 0 THEN 1 ELSE 0 END) as invalid,
                COUNT(DISTINCT protocol) as protocols
            FROM proxies
        """)
        return dict(cursor.fetchone())
    
    # ========== TARGETS ==========
    
    def add_target(self, username):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO targets (username) VALUES (?)
        """, (username,))
        self.conn.commit()
    
    def increment_target_reports(self, username):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE targets SET report_count = report_count + 1, last_reported = CURRENT_TIMESTAMP
            WHERE username = ?
        """, (username,))
        self.conn.commit()
    
    def get_target_stats(self, username):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM targets WHERE username = ?", (username,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def get_top_targets(self, limit=10):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM targets ORDER BY report_count DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    # ========== REPORT LOGS ==========
    
    def add_report_log(self, target, account_phone, status, error_message=None, response_data=None):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO report_logs (target, account_phone, status, error_message, response_data)
            VALUES (?, ?, ?, ?, ?)
        """, (target, account_phone, status, error_message, json.dumps(response_data) if response_data else None))
        self.conn.commit()
    
    def get_recent_reports(self, limit=50):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM report_logs ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_report_stats(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                COUNT(DISTINCT target) as unique_targets
            FROM report_logs
        """)
        return dict(cursor.fetchone())
    
    # ========== MAINTENANCE ==========
    
    def vacuum(self):
        """Optimise la base de données"""
        cursor = self.conn.cursor()
        cursor.execute("VACUUM")
        self.conn.commit()
        logger.info("Base de données optimisée (VACUUM)")
    
    def get_db_stats(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM accounts")
        accounts = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM proxies")
        proxies = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM targets")
        targets = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM report_logs")
        reports = cursor.fetchone()['count']
        
        return {
            "accounts": accounts,
            "proxies": proxies,
            "targets": targets,
            "report_logs": reports,
        }
    
    def close(self):
        self.conn.close()
        logger.info("Connexion DB fermée")
