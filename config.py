import os

# ========== CONFIGURATION BOT ==========
# ⚠️ REGÉNÈRE CE TOKEN VIA @BotFather (il a été exposé)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8708628597:AAEVVIO6c5wAwMRAzCl_PGttklI5lrZlV1Q")

# Liste des IDs Telegram autorisés à utiliser le bot (ADMINS)
AUTHORIZED_USERS = [int(x) for x in os.getenv("AUTHORIZED_USERS", "").split(",")]
   
# ========== CONFIGURATION TELEGRAM API ==========
# Obtiens ces infos sur https://my.telegram.org/apps
API_ID = int(os.environ.get("API_ID", "0"))  # Sera remplacé par la variable Railway
API_HASH = os.environ.get("API_HASH", "")

# Vérification au démarrage
if API_ID == 0 or not API_HASH:
    print("⚠️  ATTENTION: API_ID ou API_HASH non configurés !")
    print("⚠️  Configure les variables d'environnement API_ID et API_HASH sur Railway")
    print("⚠️  Ou édite directement ce fichier avec tes valeurs")
    
    # Valeurs de secours (à remplacer si tu ne passes pas par Railway)
    API_ID = 30062455          # ← REMPLACE PAR TON API_ID
    API_HASH = "0745b6be4969fa770f3ca5493c8e797c" # ← REMPLACE PAR TON API_HASH

DEFAULT_API_ID = API_ID
DEFAULT_API_HASH = API_HASH
SESSION_STRING = os.environ.get("SESSION_STRING", "")
