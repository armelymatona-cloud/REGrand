import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8175803085:AAEk0r0cueL9ub39zfBxl-GqSU91a5_snNo")

AUTHORIZED_USERS = [
    8045306923, 8161643057, 7842763694, 7471493416, 8008720027, 6436665202
]

API_ID = int(os.getenv("API_ID", 30062455))
API_HASH = os.getenv("API_HASH", "0745b6be4969fa770f3ca5493c8e797c")

SESSION_STRING = os.getenv("SESSION_STRING", "")

DATABASE_PATH = "regrand.db"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"
