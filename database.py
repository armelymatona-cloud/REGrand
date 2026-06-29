import json
import os
import logging
from datetime import datetime
from models import Account, Proxy, Target

logger = logging.getLogger(__name__)

DB_FILE = "database.json"


class Database:
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
            "next_id": {"account": 1, "target": 1, "proxy": 1}
        }
    
    def _save(self):
        try:
            with open(self.db_file, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"Erreur sauvegarde DB: {e}")
    
    def add_account(self, phone, api_id, api_hash):
        if phone not in self.data["accounts"]:
            acc_id = self.data["next_id"]["account"]
            self.data["next_id"]["account"] = acc_id + 1
            self.data["accounts"][phone] = {
                "id": acc_id,
                "phone": phone,
                "session_string": "",
                "api_id": api_id,
                "api_hash": api_hash,
                "proxy": None,
                "is_active": False,
                "created_at": datetime.now().isoformat(),
                "last_used": None
            }
            self._save()
            return acc_id
        return self.data["accounts"][phone]["id"]
    
    def update_account_session(self, phone, session_string):
        if phone in self.data["accounts"]:
            self.data["accounts"][phone]["session_string"] = session_string
            self.data["accounts"][phone]["last_used"] = datetime.now().isoformat()
            self._save()
    
    def update_account_status(self, phone, is_active):
        if phone in self.data["accounts"]:
            self.data["accounts"][phone]["is_active"] = is_active
            self._save()
    
    def remove_account(self, phone):
        if phone in self.data["accounts"]:
            del self.data["accounts"][phone]
            self._save()
    
    def get_account(self, phone):
        acc = self.data["accounts"].get(phone)
        return Account(**acc) if acc else None
    
    def get_all_accounts(self):
        return [Account(**a) for a in self.data["accounts"].values()]
    
    def get_active_accounts(self):
        return [Account(**a) for a in self.data["accounts"].values() if a.get("is_active")]
    
    def get_account_session(self, phone):
        acc = self.data["accounts"].get(phone)
        return acc.get("session_string", "") if acc else None
    
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
    
    def add_target(self, target_id):
        if target_id not in self.data["targets"]:
            tgt_id = self.data["next_id"]["target"]
            self.data["next_id"]["target"] = tgt_id + 1
            self.data["targets"][target_id] = {
                "id": tgt_id,
                "target_id": target_id,
                "reports_count": 0,
                "last_reported": None,
                "created_at": datetime.now().isoformat()
            }
            self._save()
    
    def increment_target_reports(self, target_id):
        if target_id in self.data["targets"]:
            self.data["targets"][target_id]["reports_count"] += 1
            self.data["targets"][target_id]["last_reported"] = datetime.now().isoformat()
            self._save()
    
    def add_proxies(self, proxy_list):
        existing = set(self.data["proxies"])
        new_count = 0
        for p in proxy_list:
            if p not in existing:
                existing.add(p)
                self.data["proxies"].append(p)
                new_count += 1
        if new_count > 0:
            logger.info(f"Batch: {new_count} proxies ajoutés")
            self._save()
        return new_count
    
    def get_proxy_count(self):
        return len(self.data["proxies"])
    
    def get_proxies(self, limit=100):
        return self.data["proxies"][:limit]
