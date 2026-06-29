import logging
import asyncio
import random

from telethon import TelegramClient
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.functions.account import ReportPeerRequest
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.types import InputReportReasonSpam, InputReportReasonViolence, InputReportReasonOther

logger = logging.getLogger(__name__)


class Reporter:
    def __init__(self, db):
        self.db = db

    async def coordinated_report(self, clients: list, target_username: str) -> int:
        target = target_username.strip().lstrip("@")
        logger.info(f"🎯 Signalement coordonné de @{target} ({len(clients)} comptes)")

        success = 0
        for client, me in clients:
            try:
                ok = await self._report_single(client, me, target)
                if ok:
                    success += 1
                await asyncio.sleep(random.uniform(2, 5))
            except Exception as e:
                logger.error(f"❌ Erreur avec {getattr(me, 'first_name', '?')}: {e}")

        logger.info(f"✅ Terminé: {success}/{len(clients)} pour @{target}")
        return success

    async def _report_single(self, client: TelegramClient, me, target_username: str) -> bool:
        try:
            target = await client.get_entity(target_username)

            raisons = [InputReportReasonSpam(), InputReportReasonViolence(), InputReportReasonOther()]

            for raison in raisons:
                try:
                    await client(ReportPeerRequest(peer=target, reason=raison, message="Spam"))
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                except Exception:
                    continue

            try:
                msg = await client.send_message(target, ".")
                await asyncio.sleep(1)
                try:
                    await client(ReportRequest(peer=target, id=[msg.id], reason=InputReportReasonSpam()))
                except Exception:
                    pass
                try:
                    await client.delete_messages(target, [msg.id])
                except Exception:
                    pass
            except Exception:
                pass

            try:
                await client(BlockRequest(id=target))
                await asyncio.sleep(1)
                await client(UnblockRequest(id=target))
            except Exception:
                pass

            return True

        except Exception as e:
            logger.error(f"❌ Erreur dans _report_single: {e}")
            return False
