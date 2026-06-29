import logging
import asyncio
import random

from telethon.tl.functions.messages import ReportSpam, Report
from telethon.tl.functions.account import ReportPeer
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

            # --- Méthode 1 : ReportPeer (signalement direct via account) ---
            try:
                # On utilise plusieurs raisons pour cumuler les reports
                reasons = [
                    InputReportReasonSpam(),
                    InputReportReasonViolence(),
                    InputReportReasonOther(),
                ]
                for reason in reasons:
                    try:
                        await client(ReportPeer(
                            peer=target,
                            reason=reason,
                            message="Spam / contenu abusif"
                        ))
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    except Exception:
                        continue
                logger.info(f"✅ ReportPeer réussi pour @{target_username}")
                return True
            except Exception as e:
                logger.debug(f"ReportPeer échoué: {e}")

            # --- Méthode 2 : messages.Report ---
            try:
                # Envoyer un message d'abord pour pouvoir le signaler
                msg = await client.send_message(target, ".")
                await asyncio.sleep(random.uniform(0.5, 1.5))

                await client(ReportSpam(peer=target))
                await asyncio.sleep(random.uniform(0.5, 1))

                # Signaler le message spécifiquement
                try:
                    await client(Report(
                        peer=target,
                        id=[msg.id],
                        reason=InputReportReasonSpam()
                    ))
                except Exception:
                    pass

                # Nettoyer
                try:
                    await client.delete_messages(target, [msg.id])
                except Exception:
                    pass

                logger.info(f"✅ ReportSpam réussi pour @{target_username}")
                return True
            except Exception as e:
                logger.debug(f"ReportSpam échoué: {e}")

            # --- Méthode 3 : Block/Unblock (moins efficace mais ne coûte rien) ---
            try:
                from telethon.tl.functions.contacts import Block, Unblock
                await client(Block(id=target))
                await asyncio.sleep(random.uniform(1, 2))
                await client(Unblock(id=target))
                logger.info(f"✅ Block/Unblock réussi pour @{target_username}")
                return True
            except Exception as e:
                logger.debug(f"Block/Unblock échoué: {e}")

            return False

        except Exception as e:
            logger.error(f"❌ Erreur dans _report_single: {e}")
            return False
