# Contenu de config.py
import os

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8708628597:AAEVVIO6c5wAwMRAzCl_PGttklI5lrZlV1Q")

# Liste des IDs Telegram autorisés à utiliser le bot (ADMINS)
AUTHORIZED_USERS = [int(x) for x in os.getenv("AUTHORIZED_USERS", "").split(",")]

# ========== CONFIGURATION TELEGRAM API ==========
# Obtiens ces infos sur https://my.telegram.org/apps
# ⚠️ NE LAISSE PAS DE VALEURS VIDES
API_ID = int(os.environ.get("API_ID", "30062455"))      # ← Mets ton vrai API_ID ici
API_HASH = os.environ.get("API_HASH", "0745b6be4969fa770f3ca5493c8e797c")   # ← Mets ton vrai API_HASH ici

# Alias pour compatibilité avec le code existant
DEFAULT_API_ID = API_ID
DEFAULT_API_HASH = API_HASH

# Session string optionnelle (pour restoration, laissé vide)
SESSION_STRING = os.environ.get("SESSION_STRING", "1BJWap1wBuwkeR-K27u6AleUDiQnL87jV70campTgUfRL7zi9k-YKvR_b03AfWai22IlRIGX2ajoRXYw5T8q8PtHK62wY_s_i8XbZhAkC-BLfb3XmoIX-PW31e6GQ-ROfKhSGbMK755ZsH78RrQkUxfDgFU1lgjYpBo2BfKfF7ArmYbIJhMe0Eyg9BaLxew1e-Kn2qsGaF94ZiVoxdAHMJW3GEBAcYiXMQG3-fl2zZbvw26qbZCTDd9cXf5YEcFOUvguJz4dg2RmqcxSXlt80r25YzwplK62c6leKZrTeIT-_o1M4YKNh8m3XLAL6PViR6TPyCf6ujOeGr3u6Qln1MverhwB4sdM=")
