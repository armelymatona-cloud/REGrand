import os
import sys

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# ========== LISTE DES ADMINS ==========
# Soit depuis une variable d'environnement (ex: "123456789,987654321")
# Soit en dur dans le code
AUTHORIZED_USERS_STR = os.environ.get("AUTHORIZED_USERS", "")

if AUTHORIZED_USERS_STR:
    # Depuis la variable d'environnement
    AUTHORIZED_USERS = [int(x.strip()) for x in AUTHORIZED_USERS_STR.split(",") if x.strip()]
else:
    # En dur dans le code
    AUTHORIZED_USERS = [
        123456789,  # Remplace par TON ID Telegram
    ]

# ========== CONFIGURATION TELEGRAM API ==========
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")

# Session string (pour le compte admin principal)
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# ========== VÉRIFICATIONS ==========
if not BOT_TOKEN:
    print("❌ ERREUR FATALE : BOT_TOKEN manquant dans les variables d'environnement")
    sys.exit(1)

if API_ID == 0 or not API_HASH:
    print("❌ ERREUR FATALE : API_ID ou API_HASH manquant dans les variables d'environnement")
    sys.exit(1)

if not AUTHORIZED_USERS:
    print("❌ ERREUR FATALE : AUTHORIZED_USERS vide")
    sys.exit(1)

print(f"✅ Configuration chargée : API_ID={API_ID}")
print(f"✅ SESSION_STRING : {'présente' if SESSION_STRING else 'ABSENTE'}")
print(f"✅ AUTHORIZED_USERS : {AUTHORIZED_USERS}")
