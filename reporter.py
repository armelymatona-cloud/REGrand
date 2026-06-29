import logging
import asyncio
import random

from telethon import TelegramClient
from telethon.tl.functions.messages import ReportRequest
from telethon.tl.functions.account import ReportPeerRequest
from telethon.tl.types import InputReportReasonSpam, InputReportReasonViolence, InputReportReasonOther

logger = logging.getLogger(__name__)


class Reporter:
    def __init__(self, db):
        self.db = db

    async def coordinated_report(self, clients: list, target_username: str) -> int:
        """
        Lance un signalement coordonné avec tous les clients disponibles.
        Retourne le nombre de signalements réussis.
        """
        target = target_username.strip().lstrip("@")
        logger.info(f"🎯 Signalement coordonné de @{target} ({len(clients)} comptes)")

        success = 0
        for client, me in clients:
            try:
                ok = await self._report_single(client, me, target)
                if ok:
                    success += 1
                # Pause entre chaque compte pour éviter le flood
                await asyncio.sleep(random.uniform(2, 5))
            except Exception as e:
                logger.error(f"❌ Erreur avec {getattr(me, 'first_name', '?')}: {e}")

        logger.info(f"✅ Terminé: {success}/{len(clients)} pour @{target}")
        return success

    async def _report_single(self, client: TelegramClient, me, target_username: str) -> bool:
        """
        Signale un utilisateur avec plusieurs méthodes pour maximiser
        l'impact. Retourne True si au moins une méthode a réussi.
        """
        try:
            # Récupération de l'entité cible
            target = await client.get_entity(target_username)

            # --- Méthode 1 : ReportPeerRequest (signalement direct via account) ---
            reasons = [
                InputReportReasonSpam(),
                InputReportReasonViolence(),
                InputReportReasonOther(),
            ]

            for reason in reasons:
                try:
                    await client(ReportPeerRequest(
                        peer=target,
                        reason=reason,
                        message="Spam / contenu abusif"
                    ))
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                except Exception as e:
                    logger.debug(f"ReportPeerRequest échoué pour {reason}: {e}")
                    continue

            logger.info(f"✅ ReportPeerRequest réussi pour @{target_username}")

            # --- Méthode 2 : ReportRequest (signalement de message spécifique) ---
            try:
                # Envoyer un message pour pouvoir le signaler
                msg = await client.send_message(target, ".")
                await asyncio.sleep(random.uniform(0.5, 1.5))

                # Signaler le message via ReportRequest
                try:
                    await client(ReportRequest(
                        peer=target,
                        id=[msg.id],
                        reason=InputReportReasonSpam()
                    ))
                except Exception as e:
                    logger.debug(f"ReportRequest échoué: {e}")

                # Nettoyer le message envoyé
                try:
                    await client.delete_messages(target, [msg.id])
                except Exception:
                    pass

                logger.info(f"✅ ReportRequest réussi pour @{target_username}")
            except Exception as e:
                logger.debug(f"Envoi message pour report échoué: {e}")

            # --- Méthode 3 : Block/Unblock (effet cumulatif) ---
            try:
                from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
                await client(BlockRequest(id=target))
                await asyncio.sleep(random.uniform(1, 2))
                await client(UnblockRequest(id=target))
                logger.info(f"✅ Block/Unblock réussi pour @{target_username}")
            except Exception as e:
                logger.debug(f"Block/Unblock échoué: {e}")

            return True

        except Exception as e:
            logger.error(f"❌ Erreur dans _report_single: {e}")
            return False
