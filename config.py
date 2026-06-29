import os

# ========== CONFIGURATION BOT ==========
# Mets ton token ici (via variable d'environnement de préférence)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8708628597:AAEVVIO6c5wAwMRAzCl_PGttklI5lrZlV1Q")

# ========== LISTE DES ADMINS (IDs Telegram) ==========
AUTHORIZED_USERS = [
    8045306923, 8161643057, 7842763694, 7471493416, 8008720027, 6436665202
]

# ========== CONFIGURATION TELEGRAM API ==========
API_ID = int(os.environ.get("API_ID", "30062455"))       # ← Ton API_ID
API_HASH = os.environ.get("API_HASH", "0745b6be4969fa770f3ca5493c8e797c") # ← Ton API_HASH

# Session string du compte admin principal (optionnel)
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# ========== CHEMINS ==========
DATABASE_PATH = "regrand.db"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"
