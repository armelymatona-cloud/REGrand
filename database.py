# database.py
import sqlite3
import json
from typing import List, Optional
from models import Account, Proxy, Target
from datetime import datetime

class Database:
    def __init__(self, db_path="bot.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                session_string TEXT,
                api_id INTEGER NOT NULL,
                api_hash TEXT NOT NULL,
                proxy TEXT,
                is_active INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used TEXT
            );
            
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT,
                password TEXT,
                protocol TEXT DEFAULT 'socks5',
                is_active INTEGER DEFAULT 1,
                last_checked TEXT
            );
            
            CREATE TABLE IF NOT EXISTS targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                reports_count INTEGER DEFAULT 0,
                last_reported TEXT,
                created_at TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS pending_logins (
                user_id INTEGER NOT NULL,
                phone TEXT NOT NULL,
                api_id INTEGER,
                api_hash TEXT,
                login_step TEXT DEFAULT 'code_sent',
                created_at TEXT NOT NULL
            );
        ''')
        
        conn.commit()
        conn.close()
    
    # --- Accounts ---
    def add_account(self, phone: str, api_id: int, api_hash: str, session_string: str = None, proxy: str = None) -> bool:
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT OR REPLACE INTO accounts (phone, api_id, api_hash, session_string, proxy, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (phone, api_id, api_hash, session_string, proxy, 1 if session_string else 0, datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            print(f"DB Error add_account: {e}")
            return False
        finally:
            conn.close()
    
    def get_all_accounts(self) -> List[Account]:
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM accounts')
        accounts = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return accounts
    
    def get_active_accounts(self) -> List[Account]:
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM accounts WHERE is_active = 1')
        accounts = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return accounts
    
    def update_account_session(self, phone: str, session_string: str):
        conn = self.get_connection()
        conn.execute('''
            UPDATE accounts SET session_string = ?, is_active = 1, last_used = ?
            WHERE phone = ?
        ''', (session_string, datetime.now().isoformat(), phone))
        conn.commit()
        conn.close()
    
    def update_account_last_used(self, phone: str):
        conn = self.get_connection()
        conn.execute('UPDATE accounts SET last_used = ? WHERE phone = ?',
                     (datetime.now().isoformat(), phone))
        conn.commit()
        conn.close()
    
    def remove_account(self, phone: str):
        conn = self.get_connection()
        conn.execute('DELETE FROM accounts WHERE phone = ?', (phone,))
        conn.commit()
        conn.close()
    
    # --- Proxies ---
    def add_proxy(self, address: str, port: int, protocol: str = "socks5",
                  username: str = None, password: str = None) -> bool:
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT OR IGNORE INTO proxies (address, port, username, password, protocol, is_active, last_checked)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            ''', (address, port, username, password, protocol, datetime.now().isoformat()))
            conn.commit()
            return True
        except:
            return False
        finally:
            conn.close()
    
    def add_proxies_bulk(self, proxies: list) -> int:
        """Ajoute plusieurs proxies, retourne le nombre ajouté"""
        conn = self.get_connection()
        count = 0
        for p in proxies:
            try:
                conn.execute('''
                    INSERT OR IGNORE INTO proxies (address, port, username, password, protocol, is_active, last_checked)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                ''', (p['address'], p['port'], p.get('username'), p.get('password'),
                      p.get('protocol', 'socks5'), datetime.now().isoformat()))
                count += 1
            except:
                pass
        conn.commit()
        conn.close()
        return count
    
    def get_active_proxies(self) -> List[Proxy]:
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM proxies WHERE is_active = 1')
        proxies = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return proxies
    
    def get_proxy_count(self) -> int:
        conn = self.get_connection()
        cursor = conn.execute('SELECT COUNT(*) as count FROM proxies WHERE is_active = 1')
        count = cursor.fetchone()['count']
        conn.close()
        return count
    
    def disable_proxy(self, proxy_id: int):
        conn = self.get_connection()
        conn.execute('UPDATE proxies SET is_active = 0 WHERE id = ?', (proxy_id,))
        conn.commit()
        conn.close()
    
    # --- Pending Logins ---
    def set_pending_login(self, user_id: int, phone: str, api_id: int, api_hash: str, step: str = "code_sent"):
        conn = self.get_connection()
        conn.execute('''
            INSERT OR REPLACE INTO pending_logins (user_id, phone, api_id, api_hash, login_step, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, phone, api_id, api_hash, step, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def get_pending_login(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM pending_logins WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    def remove_pending_login(self, user_id: int):
        conn = self.get_connection()
        conn.execute('DELETE FROM pending_logins WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    # --- Targets ---
    def add_target(self, target_id: str):
        conn = self.get_connection()
        conn.execute('''
            INSERT OR IGNORE INTO targets (target_id, created_at)
            VALUES (?, ?)
        ''', (target_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def increment_target_reports(self, target_id: str):
        conn = self.get_connection()
        conn.execute('''
            UPDATE targets SET reports_count = reports_count + 1, last_reported = ?
            WHERE target_id = ?
        ''', (datetime.now().isoformat(), target_id))
        conn.commit()
        conn.close()
    
    def get_target_stats(self, target_id: str):
        conn = self.get_connection()
        cursor = conn.execute('SELECT * FROM targets WHERE target_id = ?', (target_id,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None