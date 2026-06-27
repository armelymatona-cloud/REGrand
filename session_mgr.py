# session_mgr.py
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from typing import Optional, Tuple
from database import Database
from model import Account

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self, db: Database):
        self.db = db
        self.clients = {}  # phone -> (client, proxy_str)
    
    def build_proxy_dict(self, proxy: dict) -> Optional[dict]:
        """Construit le dict proxy pour Telethon"""
        if not proxy:
            return None
        return {
            'proxy_type': proxy['protocol'],
            'addr': proxy['address'],
            'port': proxy['port'],
            'username': proxy['username'],
            'password': proxy['password']
        }
    
    def get_proxy_for_account(self, index: int, total: int) -> Optional[dict]:
        """Assigne un proxy différent à chaque compte (round-robin)"""
        proxies = self.db.get_active_proxies()
        if not proxies:
            return None
        proxy = proxies[index % len(proxies)]
        return self.build_proxy_dict(proxy)
    
    async def create_client(self, account: Account) -> TelegramClient:
        """Crée un client Telethon avec proxy"""
        proxy = self.get_proxy_for_account(account['id'], len(self.db.get_active_accounts()))
        
        client = TelegramClient(
            StringSession(account['session_string']) if account['session_string'] else StringSession(),
            account['api_id'],
            account['api_hash'],
            proxy=proxy,
            device_model="Desktop",
            system_version="Windows 11",
            app_version="10.15.0",
            lang_code="fr"
        )
        
        return client
    
    async def connect_account(self, account: Account) -> Tuple[bool, Optional[str]]:
        """Connecte un compte existant"""
        try:
            client = await self.create_client(account)
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.warning(f"⚠️ {account['phone']} session invalide, reconnexion nécessaire")
                await client.disconnect()
                return False, "session_expired"
            
            self.clients[account['phone']] = (client, account.get('proxy'))
            self.db.update_account_last_used(account['phone'])
            logger.info(f"✅ {account['phone']} connecté")
            return True, None
            
        except Exception as e:
            logger.error(f"❌ {account['phone']}: {e}")
            return False, str(e)
    
    async def load_all_active_accounts(self):
        """Charge tous les comptes actifs de la DB"""
        accounts = self.db.get_active_accounts()
        for account in accounts:
            if account['session_string']:
                await self.connect_account(account)
        
        logger.info(f"📊 {len(self.clients)}/{len(accounts)} comptes connectés")
    
    async def start_login(self, phone: str, api_id: int, api_hash: str) -> Tuple[bool, str, Optional[TelegramClient]]:
        """Démarre le processus de login"""
        proxy = self.get_proxy_for_account(0, 999)
        
        client = TelegramClient(
            StringSession(),
            api_id,
            api_hash,
            proxy=proxy,
            device_model="Desktop",
            system_version="Windows 11",
            app_version="10.15.0"
        )
        
        await client.connect()
        
        try:
            sent = await client.send_code_request(phone)
            self.clients[phone] = (client, proxy)
            logger.info(f"📱 Code envoyé à {phone}")
            return True, f"Code envoyé à {phone}", client
        except Exception as e:
            await client.disconnect()
            return False, f"Erreur: {str(e)}", None
    
    async def verify_code(self, phone: str, code: str) -> Tuple[bool, str, Optional[str]]:
        """Vérifie le code SMS"""
        client, proxy = self.clients.get(phone, (None, None))
        if not client:
            return False, "Aucun login en cours pour ce numéro. Fais /add d'abord.", None
        
        try:
            await client.sign_in(phone, code)
            session_string = client.session.save()
            logger.info(f"✅ {phone} connecté avec succès")
            return True, "Connexion réussie!", session_string
        except SessionPasswordNeededError:
            # 2FA activée
            pending = self.db.get_pending_login(0)  # On gère via user_id dans le bot
            if pending:
                self.db.set_pending_login(pending['user_id'], phone, pending['api_id'], pending['api_hash'], "2fa_needed")
            return False, "🔐 Authentification à deux facteurs requise. Utilise /cod2 <mot_de_passe>", None
        except Exception as e:
            return False, f"Erreur: {str(e)}", None
    
    async def verify_2fa(self, phone: str, password: str) -> Tuple[bool, str, Optional[str]]:
        """Vérifie le mot de passe 2FA"""
        client, proxy = self.clients.get(phone, (None, None))
        if not client:
            return False, "Aucun login en cours", None
        
        try:
            await client.sign_in(password=password)
            session_string = client.session.save()
            logger.info(f"✅ {phone} connecté avec 2FA")
            return True, "Connexion réussie avec 2FA!", session_string
        except Exception as e:
            return False, f"Erreur 2FA: {str(e)}", None
    
    async def get_active_clients(self) -> list:
        """Retourne la liste des (phone, client) actifs"""
        result = []
        for phone, (client, proxy) in self.clients.items():
            if client and client.is_connected():
                try:
                    await client.get_me()  # Test de validité
                    result.append((phone, client))
                except:
                    pass
        return result
    
    async def disconnect_account(self, phone: str) -> bool:
        """Déconnecte un compte"""
        if phone in self.clients:
            client, _ = self.clients[phone]
            try:
                await client.disconnect()
            except:
                pass
            del self.clients[phone]
            return True
        return False
    
    async def disconnect_all(self):
        """Déconnecte tous les comptes"""
        for phone in list(self.clients.keys()):
            await self.disconnect_account(phone)
