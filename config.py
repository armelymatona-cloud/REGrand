import os

# On récupère les valeurs depuis l'environnement Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEFAULT_API_ID = os.getenv("DEFAULT_API_ID")
DEFAULT_API_HASH = os.getenv("DEFAULT_API_HASH")

# Pour la liste des utilisateurs autorisés
auth_users_str = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = [int(u.strip()) for u in auth_users_str.split(",") if u.strip()]

# À ajouter tout en bas de votre fichier config.py
print(f"DEBUG: BOT_TOKEN chargé: {'Oui' if BOT_TOKEN else 'Non'}")
print(f"DEBUG: API_ID chargé: {'Oui' if DEFAULT_API_ID else 'Non'}")
print(f"DEBUG: Liste utilisateurs: {AUTHORIZED_USERS}")
