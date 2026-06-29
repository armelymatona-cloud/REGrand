import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
AUTHORIZED_USERS = [
    8045306923, 8161643057, 7842763694, 7471493416, 8008720027, 6436665202
]

# FORCER la valeur en dur pour contourner le problème Railway
API_ID = 30062455
API_HASH = "0745b6be4969fa770f3ca5493c8e797c"
SESSION_STRING = os.environ.get("SESSION_STRING", "")
DATABASE_PATH = "regrand.db"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"

print(f"🔑 DEBUG: API_ID={API_ID}, API_HASH={'✓' if API_HASH else '✗'}")
