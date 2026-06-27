# Contenu de config.py
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
AUTHORIZED_USERS = [int(x) for x in os.getenv("AUTHORIZED_USERS", "").split(",")]
DEFAULT_API_ID = int(os.getenv("DEFAULT_API_ID"))
DEFAULT_API_HASH = os.getenv("DEFAULT_API_HASH") # Attention à l'orthographe: HASH, pas HASD
SESSION_STRING = os.getenv("SESSION_STRING")
