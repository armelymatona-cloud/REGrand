import logging
import asyncio
import random
from telethon import functions

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
            await asyncio.sleep(random.uniform(0.5, 1.5))
            tasks.append(self._report_single(client, me, target))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if r is True:
                success += 1

        logger.info(f"✅ Signalement terminé: {success}/{len(clients)} pour @{target}")
        return success

    async def _report_single(self, client, me, target_username):
        try:
            target_entity = await client.get_entity(target_username)
            success_local = False

            # MÉTHODE 1: Block/Unblock
            try:
                await client(functions.contacts.BlockRequest(id=target_entity))
                await asyncio.sleep(random.uniform(5, 10))
                await client(functions.contacts.UnblockRequest(id=target_entity))
                success_local = True
                await asyncio.sleep(random.uniform(8, 15))
            except AttributeError:
                # Fallback pour anciennes versions
                try:
                    await client(functions.contacts.Block(id=target_entity))
                    await asyncio.sleep(random.uniform(5, 10))
                    await client(functions.contacts.Unblock(id=target_entity))
                    success_local = True
                    await asyncio.sleep(random.uniform(8, 15))
                except Exception as e2:
                    logger.debug(f"⚠️ Block fallback échoué: {e2}")
            except Exception as e:
                logger.debug(f"⚠️ Block/Unblock échoué: {e}")

            # MÉTHODE 2: Message vide
            try:
                msg = await client.send_message(target_entity, ".")
                await asyncio.sleep(random.uniform(2, 4))
                await client.delete_messages(target_entity, [msg.id])
                success_local = True
                await asyncio.sleep(random.uniform(8, 15))
            except Exception as e:
                logger.debug(f"⚠️ Message vide échoué: {e}")

            # MÉTHODE 3: Groupe temporaire (totalement optionnelle)
            try:
                chat = await client(functions.messages.CreateChatRequest(
                    users=[target_entity],
                    title=f"rpt_{random.randint(10000, 99999)}"
                ))
                chat_id = chat.chats[0].id
                await asyncio.sleep(random.uniform(3, 6))
                try:
                    await client(functions.messages.DeleteChatUserRequest(
                        chat_id=chat_id, user_id=target_entity
                    ))
                except:
                    pass
                success_local = True
                await asyncio.sleep(random.uniform(8, 15))
            except AttributeError:
                # Fallback
                try:
                    chat = await client(functions.messages.CreateChat(
                        users=[target_entity],
                        title=f"rpt_{random.randint(10000, 99999)}"
                    ))
                    chat_id = chat.chats[0].id
                    await asyncio.sleep(random.uniform(3, 6))
                    try:
                        await client(functions.messages.DeleteChatUser(
                            chat_id=chat_id, user_id=target_entity
                        ))
                    except:
                        pass
                    success_local = True
                    await asyncio.sleep(random.uniform(8, 15))
                except Exception as e2:
                    logger.debug(f"⚠️ Groupe fallback échoué: {e2}")
            except Exception as e:
                logger.debug(f"⚠️ Groupe échoué: {e}")

            return success_local

        except Exception as e:
            logger.error(f"❌ Erreur: {e}")
            return False
