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

# ========== CONFIGURATION TELEGRAM API ==========

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not API_ID or not API_HASH:
    print("❌ ERREUR FATALE : API_ID ou API_HASH manquant...")
    exit(1)

# Session string (pour le compte admin principal)
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# ========== VÉRIFICATIONS ==========
if not BOT_TOKEN:
    print("❌ ERREUR FATALE : BOT_TOKEN manquant dans les variables d'environnement")
    sys.exit(1)

if not AUTHORIZED_USERS:
    print("❌ ERREUR FATALE : AUTHORIZED_USERS vide")
    sys.exit(1)

print(f"✅ Configuration chargée : API_ID={API_ID}")
print(f"✅ SESSION_STRING : {'présente' if SESSION_STRING else 'ABSENTE'}")
print(f"✅ AUTHORIZED_USERS : {AUTHORIZED_USERS}")
