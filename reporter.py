import logging
import asyncio
import random
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
from telethon.tl.functions.messages import CreateChat, DeleteChatUser

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
            # Espacer les départs pour éviter la détection
            await asyncio.sleep(random.uniform(0.5, 1.5))
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
            # Résoudre l'entité cible
            try:
                target_entity = await client.get_entity(target_username)
            except Exception as e:
                logger.warning(f"⚠️ Impossible de résoudre @{target_username}: {e}")
                return False

            success_local = False

            # ===== MÉTHODE 1: Block/Unblock via BlockRequest/UnblockRequest =====
            try:
                await client(BlockRequest(id=target_entity))
                logger.debug(f"✅ Block réussi via {me.first_name}")
                await asyncio.sleep(random.uniform(5, 10))
                await client(UnblockRequest(id=target_entity))
                logger.debug(f"✅ Unblock réussi via {me.first_name}")
                success_local = True
                await asyncio.sleep(random.uniform(8, 15))
            except Exception as e:
                logger.debug(f"⚠️ Block/Unblock échoué: {e}")

            # ===== MÉTHODE 2: Envoyer un message vide puis l'effacer =====
            try:
                msg = await client.send_message(target_entity, " ")
                await asyncio.sleep(random.uniform(2, 4))
                await client.delete_messages(target_entity, [msg.id])
                logger.debug(f"✅ Message vide envoyé/supprimé via {me.first_name}")
                success_local = True
                await asyncio.sleep(random.uniform(8, 15))
            except Exception as e:
                logger.debug(f"⚠️ Message vide échoué: {e}")

            # ===== MÉTHODE 3: Créer un groupe temporaire =====
            try:
                chat = await client(CreateChat(
                    users=[target_entity],
                    title=f"tmp_{random.randint(10000, 99999)}"
                ))
                chat_id = chat.chats[0].id

                await asyncio.sleep(random.uniform(3, 6))
                try:
                    await client(DeleteChatUser(chat_id=chat_id, user_id=target_entity))
                except:
                    pass

                logger.debug(f"✅ Méthode groupe via {me.first_name}")
                success_local = True
                await asyncio.sleep(random.uniform(8, 15))
            except Exception as e:
                logger.debug(f"⚠️ Méthode groupe échouée: {e}")

            return success_local

        except Exception as e:
            logger.error(f"❌ Erreur avec {me.first_name}: {e}")
            return False
