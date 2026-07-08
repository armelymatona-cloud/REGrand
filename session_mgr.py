import logging
from telethon import TelegramClient
from utils import create_telegram_client

logger = logging.getLogger(__name__)


class SessionManager:
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
            logger.info(f"🗑️ Client {key} déconnecté et retiré")

    async def disconnect_all(self):
        for key in list(self.clients.keys()):
            await self.remove_client(key)

    async def load_all_active_accounts(self) -> int:
        try:
            accounts = self.db.get_active_accounts()
        except Exception as e:
            logger.error(f"Erreur chargement DB: {e}")
            accounts = []

        loaded = 0
        for acc in accounts:
            if not acc.session_string or len(acc.session_string) < 10:
                continue
            try:
                client = create_telegram_client(acc.session_string)
                await client.connect()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    self.clients[acc.phone] = (client, me)
                    loaded += 1
                    logger.info(f"✅ Session restaurée: {acc.phone}")
                else:
                    logger.warning(f"⚠️ Session invalide: {acc.phone}")
                    self.db.update_account_status(acc.phone, False)
            except Exception as e:
                logger.error(f"❌ Erreur chargement {acc.phone}: {e}")

        logger.info(f"📊 {loaded}/{len(accounts)} comptes administrateurs connectés")
        return loaded

    async def get_active_clients(self) -> list:
        return [(c, m) for c, m in self.clients.values()]
