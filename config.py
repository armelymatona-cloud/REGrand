import os
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Lecture de la variable, on sépare les IDs par une virgule dans Railway
auth_users_str = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = [int(user_id.strip()) for user_id in auth_users_str.split(",") if user_id.strip()]
