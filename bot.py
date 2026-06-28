import asyncio
import logging
import os
import sys
import random
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telethon import TelegramClient, functions, types
from telethon.errors import *
from telethon.sessions import StringSession
from config import BOT_TOKEN, AUTHORIZED_USERS, API_ID, API_HASH, SESSION_STRING
from database import Database
from session_mgr import SessionManager
from reporter import Reporter
from proxy_scraper import ProxyScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler('bot_debug.log')]
)
logger = logging.getLogger(__name__)

db = Database()
session_mgr = SessionManager(db)
reporter = Reporter(db)
proxy_scraper = ProxyScraper(db)

authorized_users = set(AUTHORIZED_USERS)

REAL_DEVICES = [
    "Samsung SM-S928B", "iPhone16,2", "Xiaomi 23127PN0CG", "Pixel 9 Pro",
    "OnePlus CPH2581", "Samsung SM-A556B", "iPhone15,3", "Xiaomi 2211133C",
    "OPPO CPH2499", "Vivo V2324A",
]
REAL_LANG_CODES = ["fr", "en", "fr-FR", "en-US"]
REAL_SYSTEM_VERSIONS = ["Android 14", "Android 13", "iOS 18.0", "iOS 17.5", "Android 12"]
REAL_APP_VERSIONS = ["10.14.5", "10.14.4", "10.13.3", "10.12.8", "11.0.0"]


def create_telegram_client(session_str, proxy=None):
    client = TelegramClient(
        StringSession(session_str), API_ID, API_HASH,
        proxy=proxy,
        device_model=random.choice(REAL_DEVICES),
        system_version=random.choice(REAL_SYSTEM_VERSIONS),
        app_version=random.choice(REAL_APP_VERSIONS),
        lang_code=random.choice(REAL_LANG_CODES),
        system_lang_code="fr",
    )
    return client


def auth_required(func):
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in authorized_users:
            await update.message.reply_text("⛔ Non autorisé.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


class ReportingAccounts:
    FILE_PATH = "reporting_accounts.json"

    def __init__(self):
        self.accounts = {}
        self.clients = {}
        self._pending = {}  # {phone: {client, phone_code_hash, ...}}

    def load(self):
        if os.path.exists(self.FILE_PATH):
            try:
                with open(self.FILE_PATH) as f:
                    self.accounts = json.load(f)
                logger.info(f"📂 {len(self.accounts)} comptes chargés")
            except:
                self.accounts = {}

    def save(self):
        with open(self.FILE_PATH, "w") as f:
            json.dump(self.accounts, f, indent=2)

    def add(self, phone, api_id, api_hash):
        self.accounts[phone] = {"api_id": int(api_id), "api_hash": api_hash}
        self.save()

    def remove(self, phone):
        self.accounts.pop(phone, None)
        self.clients.pop(phone, None)
        self._pending.pop(phone, None)
        self.save()

    def get_active_clients(self):
        return list(self.clients.values())

    async def connect_all(self):
        loaded = 0
        for phone in list(self.accounts.keys()):
            session_str = db.get_account_session(phone)
            if session_str:
                try:
                    client = create_telegram_client(session_str)
                    await client.connect()
                    if await client.is_user_authorized():
                        me = await client.get_me()
                        self.clients[phone] = (client, me)
                        loaded += 1
                except:
                    pass
        return loaded


reporting_accounts = ReportingAccounts()


# ==================== COMMANDES ====================

@auth_required
async def start(update, context):
    await update.message.reply_text(
        "🤖 **REGrand Bot**\n\n"
        "• `/add +225XXXXXXXX` — Ajouter un compte\n"
        "• `/co CODE` — Valider le code reçu\n"
        "• `/cod2 MDP` — Valider la 2FA\n"
        "• `/status` — Voir les comptes\n"
        "• `/702 @user` — Signaler\n"
        "• `/del +225XXXXXXXX` — Supprimer\n"
        "• `/scrape` — Scraper proxies\n"
        "• `/reconnect` — Tout reconnecter",
        parse_mode='Markdown'
    )

@auth_required
async def help_cmd(update, context):
    await start(update, context)


@auth_required
async def add_account(update, context):
    """/add +225XXXXXXXX [api_id] [api_hash]"""
    if not context.args:
        await update.message.reply_text("Usage : `/add +225XXXXXXXX`")
        return

    phone = context.args[0].strip()
    if not phone.startswith('+'):
        phone = '+' + phone

    if not phone[1:].isdigit() or len(phone) < 8:
        await update.message.reply_text("❌ Format invalide.")
        return

    api_id = API_ID
    api_hash = API_HASH
    if len(context.args) >= 3:
        try:
            api_id = int(context.args[1])
            api_hash = context.args[2]
        except:
            await update.message.reply_text("❌ API_ID doit être un nombre.")
            return

    # Si déjà connecté via session en base
    session_data = db.get_account_session(phone)
    if session_data:
        try:
            client = create_telegram_client(session_data)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                reporting_accounts.clients[phone] = (client, me)
                uname = me.username or "pas d'username"
                await update.message.reply_text(
                    f"✅ Compte `{phone}` reconnecté !\n👤 {me.first_name} (@{uname})",
                    parse_mode='Markdown'
                )
                return
        except:
            pass

    # Nettoyer toute demande en attente pour ce numéro
    reporting_accounts._pending.pop(phone, None)
    reporting_accounts.add(phone, api_id, api_hash)

    try:
        client = TelegramClient(StringSession(), api_id, api_hash,
                                device_model=random.choice(REAL_DEVICES),
                                system_version=random.choice(REAL_SYSTEM_VERSIONS),
                                app_version=random.choice(REAL_APP_VERSIONS),
                                lang_code=random.choice(REAL_LANG_CODES))
        await client.connect()

        # Envoyer le code
        sent = await client.send_code_request(phone)
        hash_code = sent.phone_code_hash

        reporting_accounts._pending[phone] = {
            "client": client,
            "phone_code_hash": hash_code,
            "sent_at": datetime.now()
        }

        await update.message.reply_text(
            f"📱 Code envoyé à `{phone}`\n"
            f"⏳ Utilise `/co CODE` pour valider dans les 5 min.",
            parse_mode='Markdown'
        )
        logger.info(f"📱 Code envoyé à {phone}")

    except PhoneNumberInvalidError:
        reporting_accounts.remove(phone)
        await update.message.reply_text("❌ Numéro invalide.")
    except PhoneNumberFloodError:
        await update.message.reply_text("❌ Trop de tentatives. Attends.")
    except Exception as e:
        logger.error(f"❌ Erreur: {e}", exc_info=True)
        reporting_accounts.remove(phone)
        await update.message.reply_text(f"❌ Erreur : `{str(e)[:200]}`")


@auth_required
async def verify_code(update, context):
    """/co CODE"""
    if not context.args:
        await update.message.reply_text("Usage : `/co CODE`")
        return

    code = context.args[0].strip()

    if not reporting_accounts._pending:
        await update.message.reply_text(
            "❌ Aucune demande en attente. Fais d'abord `/add +225XXXXXXXX`."
        )
        return

    phone = list(reporting_accounts._pending.keys())[-1]
    pending = reporting_accounts._pending[phone]

    client = pending["client"]
    phone_code_hash = pending["phone_code_hash"]
    sent_at = pending.get("sent_at")

    # Si le client est déconnecté, on le reconnecte
    try:
        if not client.is_connected():
            await client.connect()
    except:
        pass

    # Vérifier l'expiration
    if sent_at and (datetime.now() - sent_at).total_seconds() > 300:
        # Essayer de renvoyer un code automatiquement
        try:
            await update.message.reply_text(f"🔄 Code expiré, renvoi d'un nouveau à `{phone}`...")
            sent = await client.send_code_request(phone)
            reporting_accounts._pending[phone] = {
                "client": client,
                "phone_code_hash": sent.phone_code_hash,
                "sent_at": datetime.now()
            }
            await update.message.reply_text(
                f"📱 Nouveau code envoyé à `{phone}`\n"
                f"⏳ Utilise `/co CODE` maintenant !",
                parse_mode='Markdown'
            )
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Renvoi impossible. Redis `/add {phone}`.")
            reporting_accounts._pending.pop(phone, None)
            return

    try:
        await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash
        )

        # Succès
        session_string = client.session.save()
        db.update_account_session(phone, session_string)
        db.update_account_status(phone, True)

        me = await client.get_me()
        reporting_accounts.clients[phone] = (client, me)
        reporting_accounts._pending.pop(phone, None)

        uname = me.username or "pas d'username"
        await update.message.reply_text(
            f"✅ **Compte connecté !**\n"
            f"📱 `{phone}`\n"
            f"👤 {me.first_name} (@{uname})\n"
            f"🆔 ID: `{me.id}`",
            parse_mode='Markdown'
        )
        logger.info(f"✅ Compte {phone} connecté")

    except PhoneCodeInvalidError:
        await update.message.reply_text("❌ Code invalide. Réessaie avec `/co CODE`.")
    except PhoneCodeExpiredError:
        # Renvoi automatique
        try:
            await update.message.reply_text(f"🔄 Code expiré, renvoi d'un nouveau à `{phone}`...")
            sent = await client.send_code_request(phone)
            reporting_accounts._pending[phone] = {
                "client": client,
                "phone_code_hash": sent.phone_code_hash,
                "sent_at": datetime.now()
            }
            await update.message.reply_text(
                f"📱 Nouveau code envoyé ! Utilise `/co CODE`.",
                parse_mode='Markdown'
            )
        except:
            await update.message.reply_text(f"❌ Redis `/add {phone}`.")
            reporting_accounts._pending.pop(phone, None)
    except SessionPasswordNeededError:
        reporting_accounts._pending[phone]["need_2fa"] = True
        await update.message.reply_text(
            "🔐 2FA requise ! Utilise `/cod2 MOT_DE_PASSE`",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"❌ Erreur: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Erreur : `{str(e)[:200]}`")


@auth_required
async def verify_2fa(update, context):
    """/cod2 MOT_DE_PASSE"""
    if not context.args:
        await update.message.reply_text("Usage : `/cod2 MOT_DE_PASSE`")
        return

    password = context.args[0].strip()

    # Chercher un compte en attente de 2FA
    phone = None
    for p, data in reporting_accounts._pending.items():
        if data.get("need_2fa"):
            phone = p
            break

    if not phone:
        await update.message.reply_text("❌ Aucune demande 2FA en attente.")
        return

    pending = reporting_accounts._pending[phone]
    client = pending["client"]

    try:
        await client.sign_in(password=password)
        session_string = client.session.save()
        db.update_account_session(phone, session_string)
        db.update_account_status(phone, True)

        me = await client.get_me()
        reporting_accounts.clients[phone] = (client, me)
        reporting_accounts._pending.pop(phone, None)

        uname = me.username or "pas d'username"
        await update.message.reply_text(
            f"✅ **Compte connecté (2FA) !**\n"
            f"📱 `{phone}`\n"
            f"👤 {me.first_name} (@{uname})",
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur 2FA : `{str(e)[:200]}`")


@auth_required
async def status(update, context):
    lines = ["**📊 Statut des comptes**\n"]
    
    for phone, (client, me) in session_mgr.clients.items():
        uname = f"@{me.username}" if me and me.username else "pas d'username"
        name = f"{me.first_name}" if me else "?"
        lines.append(f"👑 **Admin** : {name} ({uname})")
    
    if not session_mgr.clients:
        lines.append("👑 Aucun admin connecté")
    
    for phone, (client, me) in reporting_accounts.clients.items():
        uname = f"@{me.username}" if me and me.username else "pas d'username"
        name = f"{me.first_name}" if me else "?"
        lines.append(f"📱 **Externe** : {phone} - {name} ({uname})")
    
    if not reporting_accounts.clients:
        lines.append("📱 Aucun compte externe connecté")
    
    lines.append(f"\n🔗 Proxys : {db.get_proxy_count()}")
    lines.append(f"🎯 Cibles : {db.get_target_count()}")
    
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')


@auth_required
async def report(update, context):
    """/702 @username"""
    if not context.args:
        await update.message.reply_text("Usage : `/702 @username`")
        return

    target = context.args[0].strip()
    all_clients = list(session_mgr.clients.values()) + list(reporting_accounts.clients.values())

    if not all_clients:
        await update.message.reply_text("⚠️ Aucun compte disponible.")
        return

    msg = await update.message.reply_text(
        f"🎯 Signalement de `{target}`\n📱 {len(all_clients)} comptes...",
        parse_mode='Markdown'
    )

    try:
        success = await reporter.coordinated_report(all_clients, target)
        db.add_target(target)
        db.increment_target_reports(target)
        await msg.edit_text(
            f"✅ **Terminé**\n🎯 `{target}`\n📊 {success}/{len(all_clients)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erreur: {e}", exc_info=True)
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}")


@auth_required
async def remove_account(update, context):
    """/del +225XXXXXXXX"""
    if not context.args:
        await update.message.reply_text("Usage : `/del +225XXXXXXXX`")
        return

    phone = context.args[0].strip()
    if not phone.startswith('+'):
        phone = '+' + phone

    if phone in reporting_accounts.accounts:
        if phone in reporting_accounts.clients:
            try:
                c, _ = reporting_accounts.clients[phone]
                await c.disconnect()
            except:
                pass
        reporting_accounts.remove(phone)
        await update.message.reply_text(f"🗑️ `{phone}` retiré.")
    else:
        await update.message.reply_text(f"❌ `{phone}` introuvable.")


@auth_required
async def scrape_proxies(update, context):
    msg = await update.message.reply_text("🕷️ Scraping...")
    count = await proxy_scraper.scrape_and_store()
    await msg.edit_text(f"✅ {count} proxies ajoutés. Total: {db.get_proxy_count()}")


@auth_required
async def reconnect(update, context):
    msg = await update.message.reply_text("🔄 Reconnexion...")
    await session_mgr.disconnect_all()
    admin_count = await session_mgr.load_all_active_accounts() or 0
    for phone in list(reporting_accounts.clients.keys()):
        try:
            c, _ = reporting_accounts.clients[phone]
            await c.disconnect()
        except:
            pass
    reporting_accounts.clients.clear()
    ext_count = await reporting_accounts.connect_all() or 0
    await msg.edit_text(f"✅ Reconnecté: {admin_count + ext_count} comptes")


# ==================== INIT ====================

async def post_init(app):
    logger.info("🚀 Démarrage...")
    os.makedirs("sessions", exist_ok=True)
    reporting_accounts.load()

    admin_count = 0
    if SESSION_STRING:
        try:
            client = create_telegram_client(SESSION_STRING)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                logger.info(f"✅ Admin: {me.first_name}")
                authorized_users.add(me.id)
                session_mgr.add_client_sync(f"admin_{me.id}", client, me)
                admin_count = 1
                db.add_account(f"+{me.id}", API_ID, API_HASH)
                db.update_account_session(f"+{me.id}", SESSION_STRING)
                db.update_account_status(f"+{me.id}", True)
            else:
                logger.error("❌ SESSION_STRING invalide")
        except Exception as e:
            logger.error(f"❌ Erreur admin: {e}")

    ext_count = await reporting_accounts.connect_all() or 0

    if db.get_proxy_count() == 0:
        try:
            await proxy_scraper.scrape_and_store()
        except:
            pass

    logger.info(f"✅ Bot prêt: {admin_count + ext_count} comptes")


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add", add_account))
    app.add_handler(CommandHandler("co", verify_code))
    app.add_handler(CommandHandler("cod2", verify_2fa))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("702", report))
    app.add_handler(CommandHandler("del", remove_account))
    app.add_handler(CommandHandler("scrape", scrape_proxies))
    app.add_handler(CommandHandler("reconnect", reconnect))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
