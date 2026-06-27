import os

# On récupère les valeurs depuis l'environnement Railway
TOKEN = os.getenv("TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# Pour la liste des utilisateurs autorisés
auth_users_str = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = [int(u.strip()) for u in auth_users_str.split(",") if u.strip()]
