import os
import sys

def get_env_or_die(var_name, friendly_name=None):
    """Récupère une variable d'environnement ou affiche une erreur claire"""
    value = os.environ.get(var_name, "")
    if not value:
        print(f"❌ ERREUR FATALE : {friendly_name or var_name} non défini")
        print(f"   Configure la variable d'environnement '{var_name}' sur Railway")
        print(f"   Ou crée un fichier .env avec : {var_name}=valeur")
        sys.exit(1)
    return value

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = get_env_or_die("BOT_TOKEN", "Token du bot Telegram")

# ========== LISTE DES ADMINS ==========
# Soit depuis une variable d'environnement (ex: "123456789,987654321")
# Soit depuis AUTHORIZED_USERS_FILE (chemin vers un fichier)
AUTHORIZED_USERS_STR = os.environ.get("AUTHORIZED_USERS", "")

if AUTHORIZED_USERS_STR:
    AUTHORIZED_USERS = [int(x.strip()) for x in AUTHORIZED_USERS_STR.split(",") if x.strip()]
else:
    # Valeur par défaut - À MODIFIER AVANT DÉPLOIEMENT
    AUTHORIZED_USERS = [
        123456789,  # Remplace par TON ID Telegram
    ]

# ========== CONFIGURATION TELEGRAM API ==========
API_ID_STR = get_env_or_die("API_ID", "API_ID (de my.telegram.org)")
try:
    API_ID = int(API_ID_STR)
except ValueError:
    print(f"❌ ERREUR : API_ID doit être un nombre, reçu : '{API_ID_STR}'")
    sys.exit(1)

API_HASH = get_env_or_die("API_HASH", "API_HASH (de my.telegram.org)")

# Session string (optionnelle)
SESSION_STRING = os.environ.get("SESSION_STRING", "")

# ========== VÉRIFICATIONS FINALES ==========
if not AUTHORIZED_USERS:
    print("❌ ERREUR FATALE : AUTHORIZED_USERS est vide")
    sys.exit(1)

print(f"✅ Configuration chargée avec succès")
print(f"   API_ID: {API_ID}")
print(f"   API_HASH: {'✓ présent' if API_HASH else '✗ manquant'}")
print(f"   BOT_TOKEN: {'✓ présent' if BOT_TOKEN else '✗ manquant'}")
print(f"   SESSION_STRING: {'✓ présent (' + str(len(SESSION_STRING)) + ' car.)' if SESSION_STRING else '⚠ absent (optionnel)'}")
print(f"   AUTHORIZED_USERS: {len(AUTHORIZED_USERS)} admin(s) configuré(s)")
