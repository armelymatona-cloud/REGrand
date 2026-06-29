import logging
import asyncio
import random

logger = logging.getLogger(__name__)


class Reporter:
    def __init__(self, db):
        self.db = db
    
    async def coordinated_report(self, clients, target_username):
        target = target_username.strip()
        if target.startswith('@'):
            target = target[1:]
        
        logger.info(f"🎯 Signalement de @{target} ({len(clients)} comptes)")
        success = 0
        
        for client, me in clients:
            try:
                ok = await self._report_single(client, me, target)
                if ok:
                    success += 1
            except Exception as e:
                logger.error(f"❌ Erreur {me.first_name}: {e}")
        
        logger.info(f"✅ {success}/{len(clients)} pour @{target}")
        return success
    
    async def _report_single(self, client, me, target_username):
        try:
            target = await client.get_entity(target_username)
            
            # Méthode 1: Block/Unblock
            try:
                from telethon.tl.functions.contacts import Block, Unblock
                await client(Block(id=target))
                await asyncio.sleep(random.uniform(1, 2))
                await client(Unblock(id=target))
                await asyncio.sleep(random.uniform(2, 4))
                return True
            except:
                pass
            
            # Méthode 2: Message vide
            try:
                msg = await client.send_message(target, ".")
                await asyncio.sleep(0.5)
                await client.delete_messages(target, [msg.id])
                await asyncio.sleep(random.uniform(2, 4))
                return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Erreur: {e}")
            return False
