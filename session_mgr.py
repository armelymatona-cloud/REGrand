import logging
import os
import json
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from config import SESSIONS_DIR, ACCOUNTS_FILE
from utils import create_telegram_client

logger = logging.getLogger(__name__)


class SessionManager:
    """Gère les sessions des comptes administrateurs (stockées en DB)."""

    def __init__(self, db):
        self.db = db
        self.clients = {}  # {phone_or_key: (client, me)}

    def add_client_sync(self, key: str, client: TelegramClient, me):
        self.clients[key] = (client, me)
        logger.info(f"✅ Compte ajouté: {key} ({me.first_name})")

    async def add_client(self, key: str, client: TelegramClient, me=None):
        if me is None:
            try:
                me = await client.get_me()
            except Exception:
                me = None
        self.clients[key] = (client, me)

    async def remove_client(self, key: str):
        if key in self.clients:
            client, _ = self.clients[key]
            try:
                await client.disconnect()
            except Exception:
                pass
            del self.clients[key]

    async def disconnect_all(self):
        for key in list(self.clients.keys()):
            await self.remove_client(key)

    async def load_all_active_accounts(self) -> int:
        """Charge tous les comptes actifs depuis la DB."""
        # Cette méthode suppose que la DB a une table 'accounts'
        # avec phone et session_string
        try:
            conn = self.db._connect()
            cur = conn.cursor()
            cur.execute("SELECT phone, session_string FROM accounts WHERE active = 1")
            rows = cur.fetchall()
            conn.close()
        except Exception:
            rows = []

        loaded = 0
        for phone, session_str in rows:
            if not session_str:
                continue
            try:
                client = create_telegram_client(session_str)
                await client.connect()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    self.clients[phone] = (client, me)
                    loaded += 1
                    logger.info(f"✅ Session restaurée: {phone}")
                else:
                    logger.warning(f"⚠️ Session invalide: {phone}")
                    # Optionnel: désactiver le compte
                    try:
                        conn = self.db._connect()
                        conn.execute(
                            "UPDATE accounts SET active = 0 WHERE phone = ?",
                            (phone,)
                        )
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"❌ Erreur chargement {phone}: {e}")

        logger.info(f"📊 {loaded}/{len(rows)} comptes administrateurs connectés")
        return loaded

    async def get_active_clients(self) -> list:
        """Retourne la liste des (client, me) actifs."""
        return [(c, m) for c, m in self.clients.values()]
