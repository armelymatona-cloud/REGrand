import logging
import asyncio
import random
from telethon.tl.functions.messages import ReportSpam
from telethon.tl.functions.contacts import Block, Unblock

logger = logging.getLogger(__name__)


class Reporter:
    """Gère le signalement coordonné de comptes Telegram"""
    
    def __init__(self, db):
        self.db = db
    
    async def coordinated_report(self, clients, target_username):
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
        try:
            try:
                target_entity = await client.get_entity(target_username)
            except Exception as e:
                logger.warning(f"⚠️ Impossible de résoudre @{target_username}: {e}")
                return False
            
            success_local = False
            
            # Méthode 1: ReportSpam
            try:
                await client(ReportSpam(peer=target_entity))
                logger.debug(f"✅ ReportSpam via {me.first_name}")
                success_local = True
                await asyncio.sleep(random.uniform(2, 4))
            except Exception as e:
                logger.debug(f"⚠️ ReportSpam échoué: {e}")
            
            # Méthode 2: Block/Unblock
            try:
                await client(Block(id=target_entity))
                await asyncio.sleep(random.uniform(1, 2))
                await client(Unblock(id=target_entity))
                logger.debug(f"✅ Block/Unblock via {me.first_name}")
                success_local = True
                await asyncio.sleep(random.uniform(2, 4))
            except Exception as e:
                logger.debug(f"⚠️ Block/Unblock échoué: {e}")
            
            return success_local
            
        except Exception as e:
            logger.error(f"❌ Erreur avec {me.first_name}: {e}")
            return False
