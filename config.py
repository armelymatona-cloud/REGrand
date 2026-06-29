import os

# ========== CONFIGURATION BOT ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8708628597:AAEVVIO6c5wAwMRAzCl_PGttklI5lrZlV1Q")

# ========== LISTE DES ADMINS ==========
AUTHORIZED_USERS = [
   8045306923, 8161643057, 7842763694, 7471493416, 8008720027, 6436665202  # ← Mets TON ID Telegram ici
]

# ========== CONFIGURATION TELEGRAM API ==========
# Lit depuis Railway, sinon utilise la valeur par défaut
try:
    API_ID = int(os.environ.get("API_ID", "30062455"))  # ← Ton API_ID en dur
except:
    API_ID = 30062455  # ← Fallback

API_HASH = os.environ.get("API_HASH", "0745b6be4969fa770f3ca5493c8e797c")  # ← Ton API_HASH en dur

# Session string
SESSION_STRING = os.environ.get("SESSION_STRING", "1BJWap1wBuwkeR-K27u6AleUDiQnL87jV70campTgUfRL7zi9k-YKvR_b03AfWai22IlRIGX2ajoRXYw5T8q8PtHK62wY_s_i8XbZhAkC-BLfb3XmoIX-PW31e6GQ-ROfKhSGbMK755ZsH78RrQkUxfDgFU1lgjYpBo2BfKfF7ArmYbIJhMe0Eyg9BaLxew1e-Kn2qsGaF94ZiVoxdAHMJW3GEBAcYiXMQG3-fl2zZbvw26qbZCTDd9cXf5YEcFOUvguJz4dg2RmqcxSXlt80r25YzwplK62c6leKZrTeIT-_o1M4YKNh8m3XLAL6PViR6TPyCf6ujOeGr3u6Qln1MverhwB4sdM=")

# ========== AFFICHAGE ==========
print(f"✅ Configuration :")
print(f"   API_ID = {API_ID}")
print(f"   API_HASH = {'✓' if API_HASH and API_HASH != 'ton_api_hash_ici' else '⚠ VALEUR PAR DÉFAUT'}")
print(f"   BOT_TOKEN = {'✓' if BOT_TOKEN else '✗ MANQUANT'}")
print(f"   SESSION_STRING = {'✓' if SESSION_STRING else '⚠ absent'}")
print(f"   ADMINS = {AUTHORIZED_USERS}")
