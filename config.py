import os
import sys

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Liste des IDs Telegram autorisés à utiliser le bot
AUTHORIZED_USERS = [int(x) for x in os.getenv("AUTHORIZED_USERS", "").split(",")]
  

# ========== CONFIGURATION TELEGRAM API ==========
DEFAULT_API_ID = int(os.environ.get("API_ID", "30062455"))
DEFAULT_API_HASH = os.environ.get("API_HASH", "0745b6be4969fa770f3ca5493c8e797c")

# Session string (optionnelle, pour restoration)
SESSION_STRING = os.environ.get("SESSION_STRING", "1BJWap1wBuwkeR-K27u6AleUDiQnL87jV70campTgUfRL7zi9k-YKvR_b03AfWai22IlRIGX2ajoRXYw5T8q8PtHK62wY_s_i8XbZhAkC-BLfb3XmoIX-PW31e6GQ-ROfKhSGbMK755ZsH78RrQkUxfDgFU1lgjYpBo2BfKfF7ArmYbIJhMe0Eyg9BaLxew1e-Kn2qsGaF94ZiVoxdAHMJW3GEBAcYiXMQG3-fl2zZbvw26qbZCTDd9cXf5YEcFOUvguJz4dg2RmqcxSXlt80r25YzwplK62c6leKZrTeIT-_o1M4YKNh8m3XLAL6PViR6TPyCf6ujOeGr3u6Qln1MverhwB4sdM=")

# Vérifications au démarrage
if not BOT_TOKEN:
    print("❌ ERREUR FATALE : BOT_TOKEN manquant dans les variables d'environnement Railway")
    sys.exit(1)

if DEFAULT_API_ID == 0 or not DEFAULT_API_HASH:
    print("❌ ERREUR FATALE : API_ID ou API_HASH manquant dans les variables d'environnement Railway")
    print("   Va sur https://my.telegram.org/apps pour obtenir tes identifiants")
    sys.exit(1)

print(f"✅ Configuration chargée : API_ID={DEFAULT_API_ID}, SESSION_STRING={'présente' if SESSION_STRING else 'absente'}")
