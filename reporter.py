import logging
import asyncio
import random
from telethon.tl.functions.messages import ReportPeer, ReportSpam
from telethon.tl.types import InputReportReasonSpam
from telethon.tl.functions.contacts import Block, Unblock

logger = logging.getLogger(__name__)


class Reporter:
    """Gère le signalement coordonné de comptes Telegram"""
    
    def __init__(self, db):
        self.db = db
    
    async def coordinated_report(self, clients, target_username):
        """
        Signale un utilisateur avec plusieurs comptes simultanément
        
        Args:
            clients: Liste de tuples (TelegramClient, User)
            target_username: Nom d'utilisateur cible (@username)
        
        Returns:
            int: Nombre de signalements réussis
        """
        target = target_username.strip()
        if target.startswith('@'):
            target = target[1:]
        
        logger.info(f"🎯 Signalement coordonné de @{target} avec {len(clients)} comptes")
        
        success = 0
        tasks = []
        
        for client, me in clients:
            tasks.append(self._report_single(client, me, target))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r in results:
            if r is True:
                success += 1
        
        logger.info(f"✅ Signalement terminé: {success}/{len(clients)} pour @{target}")
        return success
    
    async def _report_single(self, client, me, target_username):
        """Signale avec un seul compte"""
        try:
            try:
                target_entity = await client.get_entity(target_username)
            except Exception as e:
                logger.warning(f"⚠️ Impossible de résoudre @{target_username}: {e}")
                return False
            
            # Méthode 1: ReportPeer
            try:
                result = await client(ReportPeer(
                    peer=target_entity,
                    reason=InputReportReasonSpam(),
                    message="Spam account"
                ))
                if result:
                    logger.debug(f"✅ ReportPeer réussi via {me.first_name}")
                    await asyncio.sleep(random.uniform(2, 5))
                    return True
            except Exception as e1:
                logger.debug(f"⚠️ Méthode 1 échouée: {e1}")
            
            # Méthode 2: ReportSpam
            try:
                result = await client(ReportSpam(peer=target_entity))
                logger.debug(f"✅ ReportSpam réussi via {me.first_name}")
                await asyncio.sleep(random.uniform(2, 5))
                return True
            except Exception as e2:
                logger.debug(f"⚠️ Méthode 2 échouée: {e2}")
            
            # Méthode 3: Block/Unblock
            try:
                await client(Block(id=target_entity))
                await asyncio.sleep(1)
                await client(Unblock(id=target_entity))
                logger.debug(f"✅ Block/Unblock réussi via {me.first_name}")
                return True
            except Exception as e3:
                logger.debug(f"⚠️ Méthode 3 échouée: {e3}")
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Erreur signalement avec {me.first_name}: {e}")
            return False
