# reporter.py
import asyncio
import random
import logging
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.types import (
    InputReportReasonSpam, InputReportReasonViolence,
    InputReportReasonPornography, InputReportReasonChildAbuse,
    InputReportReasonOther, InputReportReasonCopyright
)
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Reporter:
    REASONS = [
        InputReportReasonSpam,
        InputReportReasonViolence,
        InputReportReasonPornography,
        InputReportReasonChildAbuse,
        InputReportReasonOther,
        InputReportReasonCopyright,
    ]
    
    MESSAGES = [
        "Ce compte spamme massivement des utilisateurs",
        "Envoi de contenu violent et haineux",
        "Compte frauduleux, usurpation d'identité",
        "Harcèlement organisé envers plusieurs personnes",
        "Contenu pédopornographique signalé",
        "Arnaque financière et phishing",
        "Diffusion de logiciels malveillants",
        "Compte bot utilisé pour de la désinformation",
    ]
    
    def __init__(self, db: Database):
        self.db = db
    
    async def report_user(self, client, target, reason=None, message=None):
        """Signale un utilisateur"""
        try:
            reason = reason or random.choice(self.REASONS)()
            message = message or random.choice(self.MESSAGES)
            
            # Résout l'entité (username ou ID)
            entity = await client.get_entity(target)
            
            # Récupère des messages récents
            from telethon.tl.functions.messages import GetHistoryRequest
            history = await client(GetHistoryRequest(
                peer=entity,
                limit=3,
                offset_id=0,
                offset_date=None,
                add_offset=0,
                max_id=0,
                min_id=0,
                hash=0
            ))
            
            msg_ids = [m.id for m in history.messages if m]
            if not msg_ids:
                msg_ids = [1]  # Fallback
            
            result = await client(ReportRequest(
                peer=entity,
                id=msg_ids,
                reason=reason,
                message=message
            ))
            
            logger.info(f"✅ Signalé {target}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur signalement {target}: {e}")
            return False
    
    async def coordinated_report(self, clients: list, target: str,
                                  delay_range: tuple = (3, 20), min_delay: float = 0.5):
        """Signalement désynchronisé"""
        tasks = []
        
        for i, (phone, client) in enumerate(clients):
            delay = random.uniform(max(delay_range[0], min_delay * i), delay_range[1] + i * 2)
            reason = random.choice(self.REASONS)()
            message = random.choice(self.MESSAGES)
            
            task = asyncio.create_task(
                self._delayed_report(client, target, delay, reason, message, phone)
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = sum(1 for r in results if r is True)
        
        logger.info(f"🎯 Coordonné: {success}/{len(clients)} sur {target}")
        return success
    
    async def _delayed_report(self, client, target, delay, reason, message, phone):
        await asyncio.sleep(delay)
        result = await self.report_user(client, target, reason, message)
        logger.info(f"⏱ {phone} après {delay:.1f}s: {'OK' if result else 'FAIL'}")
        return result