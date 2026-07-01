import os

# Token du bot Telegram — à passer UNIQUEMENT via variable d'environnement
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN est requis ! Définissez-le dans les variables d'environnement.")

# IDs Telegram des administrateurs autorisés
AUTHORIZED_USERS = [
    8045306923, 8161643057, 7842763694, 7471493416, 8008720027, 6436665202
]

# API Telegram — à passer UNIQUEMENT via variables d'environnement
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
if not API_ID or not API_HASH:
    raise ValueError("❌ API_ID et API_HASH sont requis ! Définissez-les dans les variables d'environnement.")

# Session string du compte admin principal (optionnel)
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# Chemins
DATABASE_PATH = "regrand.db"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"
