import os
import sys

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Liste des IDs Telegram autorisés
AUTHORIZED_USERS_RAW = os.environ.get("AUTHORIZED_USERS", "")
if AUTHORIZED_USERS_RAW:
    AUTHORIZED_USERS = [int(x.strip()) for x in AUTHORIZED_USERS_RAW.split(",") if x.strip()]
else:
    AUTHORIZED_USERS = []

# ========== CONFIGURATION TELEGRAM API ==========
# Accepte API_HASH ou API_HASD (correction de fautes de frappe courantes)
API_ID_STR = os.environ.get("API_ID")
API_ID = int(API_ID_STR) if API_ID_STR else 0

API_HASH = os.environ.get("API_HASH") or os.environ.get("API_HASD")  # ← fallback pour la faute de frappe
SESSION_STRING = os.environ.get("SESSION_STRING")

# ========== VÉRIFICATIONS ==========
MISSING = []
if not BOT_TOKEN:
    MISSING.append("BOT_TOKEN")
if not API_ID:
    MISSING.append("API_ID")
if not API_HASH:
    MISSING.append("API_HASH ou API_HASD")
if not SESSION_STRING:
    MISSING.append("SESSION_STRING")
if not AUTHORIZED_USERS:
    MISSING.append("AUTHORIZED_USERS")

if MISSING:
    print(f"❌ ERREUR FATALE : Variables manquantes : {', '.join(MISSING)}")
    sys.exit(1)

print(f"✅ Configuration chargée : API_ID={API_ID}, API_HASH={'présent' if API_HASH else 'manquant'}")
print(f"✅ SESSION_STRING={'présente' if SESSION_STRING else 'absente'}")
print(f"✅ {len(AUTHORIZED_USERS)} utilisateur(s) autorisé(s)")
