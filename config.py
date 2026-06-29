import os

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# ========== LISTE DES ADMINS ==========
AUTHORIZED_USERS = [
    8045306923, 8161643057, 7842763694, 7471493416, 8008720027, 6436665202
]

# ========== CONFIGURATION TELEGRAM API ==========
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")

# Session string du compte admin principal (optionnel)
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# ========== CHEMINS ==========
DATABASE_PATH = "regrand.db"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"
