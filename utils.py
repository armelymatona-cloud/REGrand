import logging
import random
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)

REAL_DEVICES = [
    "Samsung SM-S928B", "iPhone16,2", "Xiaomi 23127PN0CG",
    "Pixel 9 Pro", "OnePlus CPH2581", "Samsung SM-A556B",
    "iPhone15,3", "Xiaomi 2211133C", "OPPO CPH2499", "Vivo V2324A",
]
REAL_LANG_CODES = ["fr", "en", "fr-FR", "en-US"]
REAL_SYSTEM_VERSIONS = ["Android 14", "Android 13", "iOS 18.0", "iOS 17.5", "Android 12"]
REAL_APP_VERSIONS = ["10.14.5", "10.14.4", "10.13.3", "10.12.8", "11.0.0"]


def create_telegram_client(session_str: str = "", proxy=None) -> TelegramClient:
    """
    Crée un client Telegram avec des paramètres réalistes.
    Si session_str est vide, crée un client sans session (pour login).
    """
    device = random.choice(REAL_DEVICES)
    lang = random.choice(REAL_LANG_CODES)
    system = random.choice(REAL_SYSTEM_VERSIONS)
    app_ver = random.choice(REAL_APP_VERSIONS)

    if session_str and len(session_str) > 10:
        session = StringSession(session_str)
    else:
        session = StringSession()  # Session vide pour nouveau login

    client = TelegramClient(
        session,
        API_ID,
        API_HASH,
        device_model=device,
        lang_code=lang,
        system_version=system,
        app_version=app_ver,
        proxy=proxy,
        timeout=30,
    )
    return client
