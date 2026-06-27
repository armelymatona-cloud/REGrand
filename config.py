import os

# On récupère les valeurs depuis l'environnement Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_API_ID = os.getenv("DEFAULT_API_ID")
DEFAULT_API_HASD = os.getenv("DEFAULT_API_HASD")

# Chargement de la session depuis Railway
session_str = os.getenv("SESSION_STRING")
client = TelegramClient(StringSession(session_str), api_id, api_hasd)

# Pour la liste des utilisateurs autorisés
auth_users_str = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = [int(u.strip()) for u in auth_users_str.split(",") if u.strip()]

# À ajouter tout en bas de votre fichier config.py
print(f"DEBUG: SESSION_STRING chargé: {'Oui' if SESSION_STRING else 'Non'}")
print(f"DEBUG: Liste utilisateurs: {AUTHORIZED_USERS}")
