import logging
import asyncio
import random

logger = logging.getLogger(__name__)


class Reporter:
    def __init__(self, db):
        self.db = db

    async def coordinated_report(self, clients, target_username):
        target = target_username.strip().lstrip('@')
        logger.info(f"🎯 Signalement de @{target} avec {len(clients)} comptes")
        
        tasks = []
        for client, me in clients:
            await asyncio.sleep(random.uniform(0.5, 1.5))
            tasks.append(self._report_single(client, me, target))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success = sum(1 for r in results if r is True)
        logger.info(f"✅ {success}/{len(clients)} pour @{target}")
        return success

    async def _report_single(self, client, me, target_username):
        try:
            from telethon import functions
            target_entity = await client.get_entity(target_username)
            success = False

            # Méthode 1: Block/Unblock
            try:
                await client(functions.contacts.BlockRequest(id=target_entity))
                await asyncio.sleep(random.uniform(5, 10))
                await client(functions.contacts.UnblockRequest(id=target_entity))
                success = True
                await asyncio.sleep(random.uniform(8, 15))
            except:
                try:
                    await client(functions.contacts.Block(id=target_entity))
                    await asyncio.sleep(random.uniform(5, 10))
                    await client(functions.contacts.Unblock(id=target_entity))
                    success = True
                    await asyncio.sleep(random.uniform(8, 15))
                except Exception as e:
                    logger.debug(f"⚠️ Block échoué: {e}")

            # Méthode 2: Message vide
            try:
                msg = await client.send_message(target_entity, ".")
                await asyncio.sleep(random.uniform(2, 4))
                await client.delete_messages(target_entity, [msg.id])
                success = True
                await asyncio.sleep(random.uniform(8, 15))
            except Exception as e:
                logger.debug(f"⚠️ Message échoué: {e}")

            # Méthode 3: Groupe
            try:
                chat = await client(functions.messages.CreateChatRequest(
                    users=[target_entity],
                    title=f"r_{random.randint(10000, 99999)}"
                ))
                chat_id = chat.chats[0].id
                await asyncio.sleep(random.uniform(3, 6))
                try:
                    await client(functions.messages.DeleteChatUserRequest(
                        chat_id=chat_id, user_id=target_entity
                    ))
                except:
                    pass
                success = True
            except:
                try:
                    chat = await client(functions.messages.CreateChat(
                        users=[target_entity],
                        title=f"r_{random.randint(10000, 99999)}"
                    ))
                    chat_id = chat.chats[0].id
                    await asyncio.sleep(random.uniform(3, 6))
                    try:
                        await client(functions.messages.DeleteChatUser(
                            chat_id=chat_id, user_id=target_entity
                        ))
                    except:
                        pass
                    success = True
                except Exception as e:
                    logger.debug(f"⚠️ Groupe échoué: {e}")

            return success

        except Exception as e:
            logger.error(f"❌ Erreur: {e}")
            return False
