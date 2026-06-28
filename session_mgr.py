import logging
from telethon import TelegramClient
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)


class SessionManager:
    """Gestionnaire de sessions pour les comptes admin"""
    
    def __init__(self, db):
        self.db = db
        self.clients = {}
    
    async def add_client(self, phone, client, me=None):
        if me is None:
            try:
                me = await client.get_me()
            except:
                me = None
        self.clients[phone] = (client, me)
    
    async def remove_client(self, phone):
        if phone in self.clients:
            client, _ = self.clients[phone]
            try:
                await client.disconnect()
            except:
                pass
            del self.clients[phone]
    
    async def disconnect_all(self):
        for phone in list(self.clients.keys()):
            await self.remove_client(phone)
    
    async def load_all_active_accounts(self):
        """Charge les comptes admin actifs depuis la DB"""
        accounts = self.db.get_active_accounts()
        loaded = 0
        for acc in accounts:
            phone = acc["phone"]
            session_str = acc.get("session_string", "")
            if not session_str:
                continue
            try:
                from main import create_telegram_client
                client = create_telegram_client(session_str)
                await client.connect()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    self.clients[phone] = (client, me)
                    loaded += 1
                else:
                    self.db.update_account_status(phone, "expired")
            except Exception as e:
                logger.error(f"❌ Erreur chargement {phone}: {e}")
        
        logger.info(f"📊 {loaded}/{len(accounts)} comptes admin connectés")
        return loaded
    
    async def get_active_clients(self):
        """Retourne la liste des (client, me) actifs"""
        return [(c, m) for c, m in self.clients.values()]
    
    def add_client_sync(self, phone, client, me):
        """Ajout synchrone pour le client avec SESSION_STRING"""
        self.clients[phone] = (client, me)
        logger.info(f"✅ Compte admin ajouté: {phone} ({me.first_name})")
