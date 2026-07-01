import os

# Token du bot Telegram — à passer UNIQUEMENT via variable d'environnement
BOT_TOKEN = os.environ.get("8708628597:AAEVVIO6c5wAwMRAzCl_PGttklI5lrZlV1Q")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN est requis ! Définissez-le dans les variables d'environnement.")

# IDs Telegram des administrateurs autorisés
AUTHORIZED_USERS = [
    8045306923, 8161643057, 7842763694, 7471493416, 8008720027, 6436665202
]

# API Telegram — à passer UNIQUEMENT via variables d'environnement
API_ID = int(os.environ.get("API_ID", 30062455))
API_HASH = os.environ.get("API_HASH", "0745b6be4969fa770f3ca5493c8e797c")
if not API_ID or not API_HASH:
    raise ValueError("❌ API_ID et API_HASH sont requis ! Définissez-les dans les variables d'environnement.")

# Session string du compte admin principal (optionnel)
SESSION_STRING = os.environ.get("SESSION_STRING", "1BJWap1wBuwkeR-K27u6AleUDiQnL87jV70campTgUfRL7zi9k-YKvR_b03AfWai22IlRIGX2ajoRXYw5T8q8PtHK62wY_s_i8XbZhAkC-BLfb3XmoIX-PW31e6GQ-ROfKhSGbMK755ZsH78RrQkUxfDgFU1lgjYpBo2BfKfF7ArmYbIJhMe0Eyg9BaLxew1e-Kn2qsGaF94ZiVoxdAHMJW3GEBAcYiXMQG3-fl2zZbvw26qbZCTDd9cXf5YEcFOUvguJz4dg2RmqcxSXlt80r25YzwplK62c6leKZrTeIT-_o1M4YKNh8m3XLAL6PViR6TPyCf6ujOeGr3u6Qln1MverhwB4sdM=")

# Chemins
DATABASE_PATH = "regrand.db"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"
SESSIONS_DIR = "sessions"
ACCOUNTS_FILE = "reporting_accounts.json"
