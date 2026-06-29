import os
import sys

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", )

# Liste des IDs Telegram autorisés à utiliser le bot
AUTHORIZED_USERS = [int(x.strip()) for x in AUTHORIZED_USERS_RAW.split(",") if x.strip()]

# ========== CONFIGURATION TELEGRAM API ==========
API_ID = int(os.environ.get("API_ID", ))
API_HASH = os.environ.get("API_HASH", )

# Session string (pour le compte admin principal)
SESSION_STRING = os.environ.get("SESSION_STRING", )

# Vérifications
if not BOT_TOKEN:
    print("❌ ERREUR FATALE : BOT_TOKEN manquant")
    sys.exit(1)

if API_ID == 0 or not API_HASH:
    print("❌ ERREUR FATALE : API_ID ou API_HASH manquant")
    sys.exit(1)

print(f"✅ Configuration chargée : API_ID={API_ID}")
print(f"✅ SESSION_STRING : {'présente' if SESSION_STRING else 'ABSENTE'}")
