import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_FILE = "database.json"


class Database:
    """Base de données simplifiée en JSON"""
    
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self.data = self._load()
    
    def _load(self):
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Erreur chargement DB: {e}")
        return {
            "accounts": {},
            "targets": {},
            "proxies": [],
            "pending_logins": {},
            "settings": {}
        }
    
    def _save(self):
        try:
            with open(self.db_file, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Erreur sauvegarde DB: {e}")
    
    # ===== ACCOUNTS =====
    def add_account(self, phone, api_id, api_hash):
        if phone not in self.data["accounts"]:
            self.data["accounts"][phone] = {
                "phone": phone,
                "api_id": api_id,
                "api_hash": api_hash,
                "session_string": "",
                "status": "pending",
                "added_at": datetime.now().isoformat()
            }
            self._save()
    
    def update_account_session(self, phone, session_string):
        if phone in self.data["accounts"]:
            self.data["accounts"][phone]["session_string"] = session_string
            self._save()
    
    def update_account_status(self, phone, status):
        if phone in self.data["accounts"]:
            self.data["accounts"][phone]["status"] = status
            self._save()
    
    def remove_account(self, phone):
        if phone in self.data["accounts"]:
            del self.data["accounts"][phone]
            self._save()
    
    def get_all_accounts(self):
        return list(self.data["accounts"].values())
    
    def get_active_accounts(self):
        return [a for a in self.data["accounts"].values() if a.get("status") == "active"]
    
    def get_account_session(self, phone):
        acc = self.data["accounts"].get(phone)
        return acc.get("session_string", "") if acc else None
    
    # ===== PENDING LOGINS =====
    def set_pending_login(self, user_id, phone, api_id, api_hash, status, phone_code_hash=""):
        self.data["pending_logins"][str(user_id)] = {
            "user_id": user_id,
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "status": status,
            "phone_code_hash": phone_code_hash,
            "created_at": datetime.now().isoformat()
        }
        self._save()
    
    def get_pending_login(self, user_id):
        return self.data["pending_logins"].get(str(user_id))
    
    def remove_pending_login(self, user_id):
        if str(user_id) in self.data["pending_logins"]:
            del self.data["pending_logins"][str(user_id)]
            self._save()
    
    # ===== TARGETS =====
    def add_target(self, target):
        if target not in self.data["targets"]:
            self.data["targets"][target] = {
                "username": target,
                "reports": 0,
                "first_reported": datetime.now().isoformat()
            }
            self._save()
    
    def increment_target_reports(self, target):
        if target in self.data["targets"]:
            self.data["targets"][target]["reports"] += 1
            self.data["targets"][target]["last_reported"] = datetime.now().isoformat()
            self._save()
    
    # ===== PROXIES =====
    def add_proxies(self, proxies):
        existing = set(self.data["proxies"])
        new = [p for p in proxies if p not in existing]
        self.data["proxies"].extend(new)
        self._save()
        return len(new)
    
    def get_proxy_count(self):
        return len(self.data["proxies"])
    
    def get_proxies(self, limit=100):
        return self.data["proxies"][:limit]
