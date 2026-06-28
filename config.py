import os
import sys

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Liste des IDs Telegram autorisés à utiliser le bot
AUTHORIZED_USERS = [int(x) for x in os.getenv("AUTHORIZED_USERS", "").split(",")]
  

# ========== CONFIGURATION TELEGRAM API ==========
DEFAULT_API_ID = int(os.environ.get("API_ID"))  # Pas de fallback
DEFAULT_API_HASH = os.environ.get("API_HASH")   # Pas de fallback
SESSION_STRING = os.environ.get("SESSION_STRING")  # Pas de fallback

# Vérifications au démarrage
if not BOT_TOKEN:
    print("❌ ERREUR FATALE : BOT_TOKEN manquant dans les variables d'environnement Railway")
    sys.exit(1)

if DEFAULT_API_ID == 0 or not DEFAULT_API_HASH:
    print("❌ ERREUR FATALE : API_ID ou API_HASH manquant dans les variables d'environnement Railway")
    print("   Va sur https://my.telegram.org/apps pour obtenir tes identifiants")
    sys.exit(1)

print(f"✅ Configuration chargée : API_ID={DEFAULT_API_ID}, SESSION_STRING={'présente' if SESSION_STRING else 'absente'}")
