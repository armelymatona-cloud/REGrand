import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
AUTHORIZED_USERS = [
    8045306923, 8161643057, 7842763694, 7471493416, 8008720027, 6436665202
]

try:
    API_ID = int(os.environ.get("API_ID", "0"))
except:
    API_ID = 0

API_HASH = os.environ.get("API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "")
DATABASE_PATH = "regrand.db"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"

# Debug - ça s'affichera dans les logs Railway
print(f"🔑 DEBUG CONFIG: API_ID={API_ID}, API_HASH={'✓' if API_HASH else '✗ VIDE'}, BOT_TOKEN={'✓' if BOT_TOKEN else '✗ VIDE'}")
