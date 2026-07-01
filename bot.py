import asyncio
import logging
import os
import sys
import random
import json
import re

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError, PhoneCodeExpiredError,
    PasswordHashInvalidError, FloodWaitError,
    SessionPasswordNeededError
)
from telethon.sessions import StringSession
import httpx

from config import (
    BOT_TOKEN, AUTHORIZED_USERS, API_ID, API_HASH,
    SESSION_STRING, SESSIONS_DIR, ACCOUNTS_FILE
)
from database import Database
from session_mgr import SessionManager
from reporter import Reporter
from proxy_scraper import ProxyScraper
from utils import create_telegram_client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

db = Database()
session_mgr = SessionManager(db)
reporter = Reporter(db)
proxy_scraper = ProxyScraper(db)

authorized_users = set(AUTHORIZED_USERS)
_pending = {}  # {chat_id: {...}}


def auth_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in authorized_users:
            await update.message.reply_text("⛔ Non autorisé.")
            return
        return await func(update, context)
    return wrapper


class ReportingAccounts:
    FILE_PATH = ACCOUNTS_FILE

    def __init__(self):
        self.accounts = {}
        self.clients = {}
        self._load()

    def _load(self):
        if os.path.exists(self.FILE_PATH):
            try:
                with open(self.FILE_PATH, "r") as f:
                    self.accounts = json.load(f)
                logger.info(f"📂 {len(self.accounts)} comptes externes chargés")
            except Exception as e:
                logger.error(f"❌ Erreur chargement: {e}")
                self.accounts = {}
        else:
            self.accounts = {}

    def _save(self):
        try:
            with open(self.FILE_PATH, "w") as f:
                json.dump(self.accounts, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde: {e}")

    def add(self, phone, session_string):
        self.accounts[phone] = session_string
        self._save()
        logger.info(f"➕ Compte externe ajouté: {phone}")

    def remove(self, phone):
        if phone in self.accounts:
            del self.accounts[phone]
            self._save()
        if phone in self.clients:
            try:
                client, _ = self.clients[phone]
                asyncio.create_task(client.disconnect())
            except Exception:
                pass
            del self.clients[phone]
        logger.info(f"🗑️ Compte externe retiré: {phone}")

    async def connect_all(self) -> int:
        count = 0
        for phone, session_str in self.accounts.items():
            if session_str and len(session_str) > 10:
                try:
                    client = create_telegram_client(session_str)
                    await client.connect()
                    if await client.is_user_authorized():
                        me = await client.get_me()
                        self.clients[phone] = (client, me)
                        count += 1
                        logger.info(f"✅ Compte externe connecté: {phone}")
                    else:
                        logger.warning(f"⚠️ Session externe invalide: {phone}")
                except Exception as e:
                    logger.error(f"❌ Erreur connexion externe {phone}: {e}")
        logger.info(f"📊 {count}/{len(self.accounts)} comptes externes connectés")
        return count

    def get_active_clients(self) -> list:
        return [(c, m) for c, m in self.clients.values()]


reporting_accounts = ReportingAccounts()


async def force_delete_webhook():
    """Force la suppression de tout webhook avant le polling."""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
        async with httpx.AsyncClient() as client:
            r = await client.post(url)
            if r.status_code == 200:
                logger.info("✅ Webhook supprimé (force)")
            else:
                logger.warning(f"⚠️ Réponse deleteWebhook: {r.text}")
    except Exception as e:
        logger.warning(f"⚠️ Impossible de supprimer le webhook: {e}")


@auth_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **REGrand Bot**\n\n"
        "Commandes:\n"
        "`/add +225XXXXXXXX` - Ajouter un compte\n"
        "`/co CODE` - Vérifier le code reçu\n"
        "`/cod2 MOT_DE_PASSE` - Vérifier 2FA\n"
        "`/status` - Statut des comptes\n"
        "`/702 @username` - Signaler une cible\n"
        "`/del +225XXXXXXXX` - Supprimer un compte\n"
        "`/scrape` - Scraper des proxies\n"
        "`/reconnect` - Reconnecter tous les comptes",
        parse_mode="Markdown"
    )


@auth_required
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/add +225XXXXXXXX`", parse_mode="Markdown")
        return

    phone = context.args[0].strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    if not re.match(r'^\+\d{7,15}$', phone):
        await update.message.reply_text("❌ Format invalide. Ex: `+225XXXXXXXX`", parse_mode="Markdown")
        return

    chat_id = update.effective_chat.id

    try:
        client = create_telegram_client()
        await client.connect()
        sent = await client.send_code_request(phone)

        _pending[chat_id] = {
            "phone": phone,
            "client": client,
            "phone_code_hash": sent.phone_code_hash,
            "step": "code"
        }

        await update.message.reply_text(
            f"📱 **Code SMS envoyé** à `{phone}`.\n"
            f"📩 Vérifie tes SMS.\n"
            f"📝 Utilise `/co CODE` dès réception.\n"
            f"🔐 Si 2FA, utilise `/cod2 MOT_DE_PASSE` ensuite.",
            parse_mode="Markdown"
        )
    except FloodWaitError as e:
        await update.message.reply_text(
            f"⏳ Flood wait: attends {e.seconds}s avant de réessayer.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)[:200]}", parse_mode="Markdown")


@auth_required
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/co CODE`", parse_mode="Markdown")
        return

    code = context.args[0].strip()
    chat_id = update.effective_chat.id

    if chat_id not in _pending:
        await update.message.reply_text(
            "❌ Aucune session. Fais `/add +225XXXXXXXX` d'abord.",
            parse_mode="Markdown"
        )
        return

    pending = _pending[chat_id]
    phone = pending["phone"]
    client = pending["client"]
    phone_code_hash = pending["phone_code_hash"]

    try:
        if not client.is_connected():
            await client.connect()
    except Exception:
        pass

    try:
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)

        me = await client.get_me()
        session_str = client.session.save()

        db.save_account(phone, session_str)
        await session_mgr.add_client(phone, client, me)
        del _pending[chat_id]

        if me.id not in authorized_users:
            authorized_users.add(me.id)

        await update.message.reply_text(
            f"✅ **Compte ajouté !**\n"
            f"👤 `{me.first_name or '?'}` (ID: `{me.id}`)\n"
            f"📱 `{phone}`",
            parse_mode="Markdown"
        )

    except SessionPasswordNeededError:
        pending["step"] = "2fa"
        await update.message.reply_text(
            "🔐 2FA requis ! Utilise `/cod2 MOT_DE_PASSE`.",
            parse_mode="Markdown"
        )

    except PhoneCodeInvalidError:
        await update.message.reply_text(
            "❌ Code invalide. Vérifie dans tes SMS et réessaie avec `/co CODE`.",
            parse_mode="Markdown"
        )

    except PhoneCodeExpiredError:
        msg = await update.message.reply_text("❌ Code expiré. Nouvel envoi...", parse_mode="Markdown")
        try:
            await client.disconnect()
        except Exception:
            pass

        try:
            new_client = create_telegram_client()
            await new_client.connect()
            sent = await new_client.send_code_request(phone)

            _pending[chat_id] = {
                "phone": phone,
                "client": new_client,
                "phone_code_hash": sent.phone_code_hash,
                "step": "code"
            }

            await msg.edit_text(
                f"📱 **Nouveau SMS** envoyé à `{phone}`.\n"
                f"Envoie `/co CODE` dès réception !",
                parse_mode="Markdown"
            )
        except FloodWaitError as e:
            await msg.edit_text(
                f"⏳ Trop de tentatives. Attends {e.seconds}s puis refais `/add`.",
                parse_mode="Markdown"
            )
            del _pending[chat_id]
        except Exception as e2:
            await msg.edit_text(
                f"❌ Erreur renvoi: {str(e2)[:200]}\nRefais `/add` manuellement.",
                parse_mode="Markdown"
            )
            del _pending[chat_id]

    except FloodWaitError as e:
        await update.message.reply_text(f"⏳ Flood wait: {e.seconds}s", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)[:200]}", parse_mode="Markdown")


@auth_required
async def verify_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/cod2 MOT_DE_PASSE`", parse_mode="Markdown")
        return

    password = " ".join(context.args)
    chat_id = update.effective_chat.id

    if chat_id not in _pending:
        await update.message.reply_text(
            "❌ Aucune session. Fais `/add` d'abord.",
            parse_mode="Markdown"
        )
        return

    pending = _pending[chat_id]
    phone = pending["phone"]
    client = pending["client"]

    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        session_str = client.session.save()

        db.save_account(phone, session_str)
        await session_mgr.add_client(phone, client, me)
        del _pending[chat_id]

        if me.id not in authorized_users:
            authorized_users.add(me.id)

        await update.message.reply_text(
            f"✅ **Compte ajouté (2FA) !**\n"
            f"👤 `{me.first_name or '?'}` (ID: `{me.id}`)\n"
            f"📱 `{phone}`",
            parse_mode="Markdown"
        )
    except PasswordHashInvalidError:
        await update.message.reply_text("❌ Mot de passe 2FA invalide.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)[:200]}", parse_mode="Markdown")


@auth_required
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_clients = await session_mgr.get_active_clients()
    reporting_clients = reporting_accounts.get_active_clients()

    msg = f"**📊 STATUT**\n\n"
    msg += f"**ADMINS ({len(admin_clients)}):**\n"
    for client, me in admin_clients:
        uname = f"(@{me.username})" if me and me.username else ""
        name = me.first_name if me else "?"
        uid = me.id if me else "?"
        msg += f"✅ `{uid}` {name} {uname}\n"

    msg += f"\n**EXTERNES ({len(reporting_clients)}/{len(reporting_accounts.accounts)}):**\n"
    for client, me in reporting_clients:
        uname = f"(@{me.username})" if me and me.username else ""
        name = me.first_name if me else "?"
        uid = me.id if me else "?"
        msg += f"✅ `{uid}` {name} {uname}\n"

    msg += f"\n🔌 Proxies: {db.get_proxy_count()}"
    await update.message.reply_text(msg, parse_mode="Markdown")


@auth_required
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/702 @username`", parse_mode="Markdown")
        return

    target = context.args[0].strip()
    target_clean = target.lstrip("@").lower()

    admin_ids = set(authorized_users)
    admin_usernames = set()

    for aid in admin_ids:
        try:
            chat = await context.bot.get_chat(aid)
            if chat.username:
                admin_usernames.add(chat.username.lower())
                admin_usernames.add(f"@{chat.username.lower()}")
        except Exception:
            pass

    check = await session_mgr.get_active_clients()
    for client, me in check:
        if me:
            admin_ids.add(me.id)
            if me.username:
                admin_usernames.add(me.username.lower())
                admin_usernames.add(f"@{me.username.lower()}")

    if target_clean in admin_usernames or target_clean.replace("@", "") in admin_usernames:
        await update.message.reply_text(f"❌ `{target}` est un admin.", parse_mode="Markdown")
        return

    all_clients = []
    all_clients.extend(await session_mgr.get_active_clients())
    all_clients.extend(reporting_accounts.get_active_clients())

    if len(all_clients) < 1:
        await update.message.reply_text("⚠️ Aucun compte disponible.", parse_mode="Markdown")
        return

    msg = await update.message.reply_text(
        f"🎯 Signalement de `{target}` ({len(all_clients)} comptes)...",
        parse_mode="Markdown"
    )

    try:
        success = await reporter.coordinated_report(all_clients, target)
        db.add_target(target)
        db.increment_target_reports(target)
        await msg.edit_text(
            f"✅ **Terminé**\n🎯 `{target}`\n📊 {success}/{len(all_clients)} succès",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}", parse_mode="Markdown")


@auth_required
async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/del +225XXXXXXXX`", parse_mode="Markdown")
        return
    phone = context.args[0].strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    reporting_accounts.remove(phone)
    db.remove_account(phone)
    await update.message.reply_text(f"🗑️ `{phone}` retiré.", parse_mode="Markdown")


@auth_required
async def scrape_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🕷️ Scraping des proxies...")
    count = await proxy_scraper.scrape_and_store()
    await msg.edit_text(f"✅ {count} nouveaux. Total: {db.get_proxy_count()}", parse_mode="Markdown")


@auth_required
async def reconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Reconnexion...")
    await session_mgr.disconnect_all()
    admin_count = await session_mgr.load_all_active_accounts() or 0
    for phone in list(reporting_accounts.clients.keys()):
        try:
            client, _ = reporting_accounts.clients[phone]
            await client.disconnect()
        except Exception:
            pass
    reporting_accounts.clients.clear()
    external_count = await reporting_accounts.connect_all() or 0
    total = admin_count + external_count
    await msg.edit_text(f"✅ {total} reconnectés ({admin_count} admins, {external_count} externes)", parse_mode="Markdown")


async def post_init(app):
    # ÉTAPE 1: Forcer la suppression du webhook AVANT tout
    await force_delete_webhook()

    logger.info("🚀 Démarrage de REGrand...")
    os.makedirs(SESSIONS_DIR, exist_ok=True)

    admin_count = 0

    if SESSION_STRING and len(SESSION_STRING) > 10:
        try:
            client = create_telegram_client(SESSION_STRING)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                if me.id not in authorized_users:
                    authorized_users.add(me.id)
                session_mgr.add_client_sync(f"admin_{me.id}", client, me)
                admin_count = 1
                logger.info(f"✅ Admin principal: {me.first_name} (ID: {me.id})")
            else:
                logger.warning("⚠️ Session admin non valide")
                admin_count = await session_mgr.load_all_active_accounts() or 0
        except Exception as e:
            logger.error(f"❌ Admin principal: {e}")
            admin_count = await session_mgr.load_all_active_accounts() or 0
    else:
        logger.info("ℹ️ Pas de SESSION_STRING, chargement depuis DB...")
        admin_count = await session_mgr.load_all_active_accounts() or 0

    external_count = await reporting_accounts.connect_all() or 0

    if db.get_proxy_count() == 0:
        try:
            await proxy_scraper.scrape_and_store()
        except Exception as e:
            logger.warning(f"⚠️ Scraping: {e}")

    total = admin_count + external_count
    logger.info(f"✅ REGrand prêt: {total} comptes ({admin_count} admins, {external_count} externes)")


def main():
    logger.info("🔄 Initialisation du bot...")

    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN manquant !")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_account))
    app.add_handler(CommandHandler("co", verify_code))
    app.add_handler(CommandHandler("cod2", verify_2fa))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("702", report))
    app.add_handler(CommandHandler("del", remove_account))
    app.add_handler(CommandHandler("scrape", scrape_proxies))
    app.add_handler(CommandHandler("reconnect", reconnect))

    logger.info("🔄 Polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
