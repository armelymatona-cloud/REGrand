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
from telethon.tl.functions.contacts import Block, Unblock
from telethon.tl.functions.messages import CreateChat, AddChatUser, DeleteChatUser
from config import BOT_TOKEN, AUTHORIZED_USERS, API_ID, API_HASH, SESSION_STRING
from database import Database
from session_mgr import SessionManager
from reporter import Reporter
from proxy_scraper import ProxyScraper

# ========== LOGGING ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log')
    ]
)
logger = logging.getLogger(__name__)

# ========== INITIALISATION ==========
db = Database()
session_mgr = SessionManager(db)
reporter = Reporter(db)
proxy_scraper = ProxyScraper(db)

authorized_users = set(AUTHORIZED_USERS)
_pending = {}

# Device models réalistes (rotation aléatoire)
REAL_DEVICES = [
    "Samsung SM-S928B",
    "iPhone16,2",
    "Xiaomi 23127PN0CG",
    "Pixel 9 Pro",
    "OnePlus CPH2581",
    "Samsung SM-A556B",
    "iPhone15,3",
    "Xiaomi 2211133C",
    "OPPO CPH2499",
    "Vivo V2324A",
]

REAL_LANG_CODES = ["fr", "en", "fr-FR", "en-US"]
REAL_SYSTEM_VERSIONS = ["Android 14", "Android 13", "iOS 18.0", "iOS 17.5", "Android 12"]
REAL_APP_VERSIONS = ["10.14.5", "10.14.4", "10.13.3", "10.12.8", "11.0.0"]


# ========== FONCTIONS UTILITAIRES ==========

def create_telegram_client(session_str, proxy=None):
    """Crée un client Telethon avec des identifiants réalistes aléatoires"""
    client = TelegramClient(
        StringSession(session_str),
        API_ID,
        API_HASH,
        proxy=proxy if proxy else None,
        device_model=random.choice(REAL_DEVICES),
        system_version=random.choice(REAL_SYSTEM_VERSIONS),
        app_version=random.choice(REAL_APP_VERSIONS),
        lang_code=random.choice(REAL_LANG_CODES),
        system_lang_code="fr",
    )
    return client


def auth_required(func):
    """Décorateur : vérifie que l'utilisateur est autorisé"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in authorized_users:
            await update.message.reply_text(
                "⛔ Non autorisé. Contacte l'admin du bot."
            )
            logger.warning(f"Tentative d'accès non autorisé : user_id={user_id}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


# ========== GESTIONNAIRE DE COMPTES EXTERNES (via /add) ==========

class ReportingAccounts:
    """Gère les comptes ajoutés via /add (comptes non-admin)"""

    FILE_PATH = "reporting_accounts.json"

    def __init__(self):
        self.accounts = {}   # {phone: {"api_id": X, "api_hash": Y}}
        self.clients = {}    # {phone: (client, me)}
        self._code_requests = {}  # {phone: {"client": client, "phone_code_hash": hash}}
        self._2fa_requests = {}   # {phone: {"client": client}}

    def load(self):
        if os.path.exists(self.FILE_PATH):
            try:
                with open(self.FILE_PATH, "r") as f:
                    self.accounts = json.load(f)
                logger.info(f"📂 {len(self.accounts)} comptes externes chargés")
            except Exception as e:
                logger.error(f"❌ Erreur chargement {self.FILE_PATH}: {e}")
                self.accounts = {}

    def save(self):
        try:
            with open(self.FILE_PATH, "w") as f:
                json.dump(self.accounts, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde {self.FILE_PATH}: {e}")

    def add(self, phone, api_id, api_hash):
        self.accounts[phone] = {"api_id": int(api_id), "api_hash": api_hash}
        self.save()

    def remove(self, phone):
        if phone in self.accounts:
            del self.accounts[phone]
            self.save()

    def get(self, phone):
        return self.accounts.get(phone)

    def get_active_clients(self):
        return [(c, m) for c, m in self.clients.values()]

    async def connect_all(self):
        """Connecte tous les comptes externes enregistrés"""
        loaded = 0
        for phone, creds in self.accounts.items():
            try:
                # Vérifier si une session string existe pour ce compte
                session_data = db.get_account_session(phone) if creds.get("session") else None
                if session_data:
                    client = create_telegram_client(session_data)
                    await client.connect()
                    if await client.is_user_authorized():
                        me = await client.get_me()
                        self.clients[phone] = (client, me)
                        loaded += 1
                        logger.info(f"✅ Compte externe connecté : {phone}")
                        continue
            except Exception as e:
                logger.debug(f"⚠️ Session invalide pour {phone}: {e}")

            # Si pas de session, on skip (l'utilisateur doit refaire /add)
            logger.warning(f"⚠️ Compte {phone} non connecté (session manquante)")
        return loaded


# Instance globale des comptes externes
reporting_accounts = ReportingAccounts()


# ========== COMMANDES ==========

@auth_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    await update.message.reply_text(
        "🤖 **REGrand Bot actif**\n\n"
        "Commandes disponibles :\n"
        "• `/add +225XXXXXXXX` — Ajouter un compte externe\n"
        "• `/co CODE` — Valider le code de connexion\n"
        "• `/cod2 CODE2FA` — Valider la double authentification\n"
        "• `/status` — Voir les comptes connectés\n"
        "• `/702 @username` — Signaler un compte\n"
        "• `/del +225XXXXXXXX` — Supprimer un compte externe\n"
        "• `/scrape` — Scraper des proxies\n"
        "• `/reconnect` — Reconnecter tous les comptes\n"
        "• `/help` — Cette aide",
        parse_mode='Markdown'
    )


@auth_required
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    await start(update, context)


@auth_required
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/add +225XXXXXXXX"""
    if not context.args:
        await update.message.reply_text(
            "Usage : `/add +225XXXXXXXX`\n"
            "Utilise tes API_ID et API_HASH par défaut.\n"
            "Pour spécifier d'autres credentials : `/add +225XXXXXXXX API_ID API_HASH`",
            parse_mode='Markdown'
        )
        return

    phone = context.args[0].strip()
    if not phone.startswith('+'):
        phone = '+' + phone

    # Vérifier le format du numéro
    if not phone[1:].isdigit() or len(phone) < 8:
        await update.message.reply_text(
            "❌ Format invalide. Utilise `/add +225XXXXXXXX`",
            parse_mode='Markdown'
        )
        return

    api_id = API_ID
    api_hash = API_HASH
    if len(context.args) >= 3:
        try:
            api_id = int(context.args[1])
            api_hash = context.args[2]
        except ValueError:
            await update.message.reply_text(
                "❌ API_ID doit être un nombre. Usage : `/add +225XXXXXXXX API_ID API_HASH`",
                parse_mode='Markdown'
            )
            return

    # Enregistrer le compte
    reporting_accounts.add(phone, api_id, api_hash)

    # Envoyer le code
    try:
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()

        sent = await client.send_code_request(phone)
        phone_code_hash = sent.phone_code_hash

        # Stocker la demande
        reporting_accounts._code_requests[phone] = {
            "client": client,
            "phone_code_hash": phone_code_hash,
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash
        }

        await update.message.reply_text(
            f"📱 Code envoyé à `{phone}`\n"
            f"Utilise `/co CODE` pour valider.",
            parse_mode='Markdown'
        )
        logger.info(f"📱 Code envoyé à {phone}")
    except Exception as e:
        logger.error(f"❌ Erreur envoi code à {phone}: {e}", exc_info=True)
        reporting_accounts.remove(phone)
        await update.message.reply_text(
            f"❌ Impossible d'envoyer le code : `{str(e)[:200]}`",
            parse_mode='Markdown'
        )


@auth_required
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/co CODE"""
    if not context.args:
        await update.message.reply_text("Usage : `/co CODE`", parse_mode='Markdown')
        return

    code = context.args[0].strip()

    # Chercher la demande de code la plus récente
    if not reporting_accounts._code_requests:
        await update.message.reply_text(
            "❌ Aucune demande de code en attente. Fais d'abord `/add +225XXXXXXXX`",
            parse_mode='Markdown'
        )
        return

    phone = list(reporting_accounts._code_requests.keys())[-1]
    req = reporting_accounts._code_requests[phone]

    try:
        client = req["client"]
        phone_code_hash = req["phone_code_hash"]

        await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash
        )

        # Succès : récupérer la session string
        session_string = client.session.save()
        db.update_account_session(phone, session_string)

        me = await client.get_me()
        reporting_accounts.clients[phone] = (client, me)

        # Nettoyer
        del reporting_accounts._code_requests[phone]

        await update.message.reply_text(
            f"✅ Compte `{phone}` connecté !\n"
            f"👤 {me.first_name} (@{me.username})",
            parse_mode='Markdown'
        )
        logger.info(f"✅ Compte {phone} connecté avec succès")
    except PhoneCodeInvalidError:
        await update.message.reply_text("❌ Code invalide. Réessaie avec `/co CODE`", parse_mode='Markdown')
    except SessionPasswordNeededError:
        # 2FA requis
        reporting_accounts._2fa_requests[phone] = {"client": client}
        await update.message.reply_text(
            "🔐 Code valide ! Mais le compte a une double authentification.\n"
            "Utilise `/cod2 MOT_DE_PASSE`",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"❌ Erreur vérification code {phone}: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Erreur : `{str(e)[:200]}`",
            parse_mode='Markdown'
        )


@auth_required
async def verify_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cod2 MOT_DE_PASSE"""
    if not context.args:
        await update.message.reply_text("Usage : `/cod2 MOT_DE_PASSE`", parse_mode='Markdown')
        return

    if not reporting_accounts._2fa_requests:
        await update.message.reply_text(
            "❌ Aucune demande 2FA en attente.",
            parse_mode='Markdown'
        )
        return

    password = context.args[0].strip()
    phone = list(reporting_accounts._2fa_requests.keys())[-1]
    req = reporting_accounts._2fa_requests[phone]
    client = req["client"]

    try:
        await client.sign_in(password=password)
        session_string = client.session.save()
        db.update_account_session(phone, session_string)

        me = await client.get_me()
        reporting_accounts.clients[phone] = (client, me)

        del reporting_accounts._2fa_requests[phone]

        await update.message.reply_text(
            f"✅ Compte `{phone}` connecté (via 2FA) !\n"
            f"👤 {me.first_name} (@{me.username})",
            parse_mode='Markdown'
        )
        logger.info(f"✅ Compte {phone} connecté avec 2FA")
    except Exception as e:
        logger.error(f"❌ Erreur 2FA {phone}: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Mot de passe 2FA invalide : `{str(e)[:200]}`",
            parse_mode='Markdown'
        )


@auth_required
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status"""
    lines = ["**📊 Statut des comptes**\n"]

    # Comptes admin (session_mgr)
    admin_clients = session_mgr.get_clients() if hasattr(session_mgr, 'get_clients') else list(session_mgr.clients.items())
    admin_count = 0
    for phone, (client, me) in session_mgr.clients.items():
        admin_count += 1
        uname = f"@{me.username}" if me and me.username else "pas d'username"
        name = f"{me.first_name} {me.last_name or ''}" if me else "?"
        lines.append(f"👑 **Admin #{admin_count}** : {name} ({uname})")

    if admin_count == 0:
        lines.append("👑 Aucun compte admin connecté")

    lines.append("")

    # Comptes externes
    ext_count = 0
    for phone, (client, me) in reporting_accounts.clients.items():
        ext_count += 1
        uname = f"@{me.username}" if me and me.username else "pas d'username"
        name = f"{me.first_name} {me.last_name or ''}" if me else "?"
        lines.append(f"📱 **Externe #{ext_count}** : {phone} — {name} ({uname})")

    if ext_count == 0:
        lines.append("📱 Aucun compte externe connecté")

    lines.append("")
    lines.append(f"🔗 Proxys disponibles : {db.get_proxy_count()}")
    lines.append(f"🎯 Cibles signalées : {db.get_target_count()}")

    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')


@auth_required
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/702 @username"""
    if not context.args:
        await update.message.reply_text("Usage : `/702 @username`", parse_mode='Markdown')
        return

    target_username = context.args[0].strip()

    # Vérifier que la cible n'est pas un admin
    admin_ids = set()
    for phone, (client, me) in session_mgr.clients.items():
        if me and me.id:
            admin_ids.add(me.id)

    # Vérification par ID
    admin_clients_list = await session_mgr.get_active_clients()
    if admin_clients_list:
        try:
            client, _ = admin_clients_list[0]
            target_entity = await client.get_entity(target_username)
            if hasattr(target_entity, 'id') and target_entity.id in admin_ids:
                await update.message.reply_text(
                    "❌ **Signalement BLOQUÉ !** Cet utilisateur est un admin du bot.",
                    parse_mode='Markdown'
                )
                return
        except:
            pass

    # Récupérer TOUS les comptes
    all_clients = []

    admin_clients = await session_mgr.get_active_clients()
    all_clients.extend(admin_clients)

    reporting_clients_list = reporting_accounts.get_active_clients()
    all_clients.extend(reporting_clients_list)

    if len(all_clients) < 1:
        await update.message.reply_text(
            "⚠️ Aucun compte disponible. Ajoutes-en avec `/add`.",
            parse_mode='Markdown'
        )
        return

    msg = await update.message.reply_text(
        f"🎯 Signalement de `{target_username}`\n"
        f"📱 {len(all_clients)} comptes mobilisés...",
        parse_mode='Markdown'
    )

    try:
        success = await reporter.coordinated_report(all_clients, target_username)

        db.add_target(target_username)
        db.increment_target_reports(target_username)

        await msg.edit_text(
            f"✅ **Signalement terminé**\n"
            f"🎯 `{target_username}`\n"
            f"📊 {success}/{len(all_clients)} signalements réussis",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erreur report: {e}", exc_info=True)
        await msg.edit_text(f"❌ Erreur : {str(e)[:200]}", parse_mode='Markdown')


@auth_required
async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/del +225XXXXXXXX"""
    if not context.args:
        await update.message.reply_text("Usage : `/del +225XXXXXXXX`", parse_mode='Markdown')
        return

    phone = context.args[0].strip()
    if not phone.startswith('+'):
        phone = '+' + phone

    if phone in reporting_accounts.accounts:
        # Déconnecter si connecté
        if phone in reporting_accounts.clients:
            try:
                client, _ = reporting_accounts.clients[phone]
                await client.disconnect()
            except:
                pass
            del reporting_accounts.clients[phone]

        reporting_accounts.remove(phone)
        await update.message.reply_text(f"🗑️ `{phone}` retiré.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ `{phone}` introuvable.", parse_mode='Markdown')


@auth_required
async def scrape_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scrape"""
    msg = await update.message.reply_text("🕷️ Scraping des proxies en cours...")
    count = await proxy_scraper.scrape_and_store()
    valid = db.get_proxy_count()
    await msg.edit_text(
        f"✅ {count} nouveaux proxies ajoutés. Total : {valid}",
        parse_mode='Markdown'
    )


@auth_required
async def reconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reconnect"""
    msg = await update.message.reply_text("🔄 Reconnexion de tous les comptes...")

    # Déconnecter les comptes admin
    await session_mgr.disconnect_all()
    admin_count = await session_mgr.load_all_active_accounts()
    if admin_count is None:
        admin_count = 0

    # Déconnecter les comptes externes
    for phone in list(reporting_accounts.clients.keys()):
        try:
            client, _ = reporting_accounts.clients[phone]
            await client.disconnect()
        except:
            pass
    reporting_accounts.clients.clear()
    external_count = await reporting_accounts.connect_all()
    if external_count is None:
        external_count = 0

    await msg.edit_text(
        f"✅ Reconnecté : {admin_count + external_count} comptes "
        f"({admin_count} admin + {external_count} externes)",
        parse_mode='Markdown'
    )


# ========== INITIALISATION ==========

async def post_init(app: Application):
    """Fonction exécutée après le démarrage du bot"""
    logger.info("🚀 Démarrage du bot REGrand...")

    os.makedirs("sessions", exist_ok=True)

    # Charger les comptes externes depuis le fichier JSON
    reporting_accounts.load()

    # 1. Charger le compte admin via SESSION_STRING
    admin_count = 0
    if SESSION_STRING:
        try:
            logger.info("👤 Connexion du compte admin via SESSION_STRING...")
            # Utiliser un proxy si disponible
            proxy = None
            proxy_str = db.get_random_proxy()
            if proxy_str:
                proxy_parts = proxy_str.split(":")
                if len(proxy_parts) == 2:
                    from telethon.network.connection import ConnectionTcpMTProxy
                    proxy_type_mt = None

            client = create_telegram_client(SESSION_STRING, proxy=proxy)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                logger.info(f"✅ Admin connecté: {me.first_name} (@{me.username}) - ID: {me.id}")

                # Ajouter l'ID aux autorisés s'il n'y est pas
                if me.id not in authorized_users:
                    logger.warning(f"⚠️ L'ID {me.id} n'est pas dans AUTHORIZED_USERS, ajout automatique")
                    authorized_users.add(me.id)

                # Stocker dans session_mgr pour qu'il soit utilisé par /702
                session_mgr.add_client_sync(f"admin_{me.id}", client, me)
                admin_count = 1

                # Sauvegarder aussi dans la DB
                phone_display = f"+{me.id}"
                db.add_account(phone_display, API_ID, API_HASH)
                db.update_account_session(phone_display, SESSION_STRING)
                db.update_account_status(phone_display, True)
            else:
                logger.error("❌ SESSION_STRING invalide ou expirée")
                await client.disconnect()
        except Exception as e:
            logger.error(f"❌ Erreur connexion admin: {e}", exc_info=True)
    else:
        logger.warning("⚠️ Aucune SESSION_STRING configurée, pas de compte admin automatique")
        # Fallback : charger depuis la DB
        admin_count = await session_mgr.load_all_active_accounts()
        if admin_count is None:
            admin_count = 0

    # 2. Charger les comptes externes
    external_count = await reporting_accounts.connect_all()
    if external_count is None:
        external_count = 0

    # 3. Scraper les proxies si aucun en base
    if db.get_proxy_count() == 0:
        logger.info("🔌 Scraping des proxies...")
        try:
            await proxy_scraper.scrape_and_store()
        except Exception as e:
            logger.warning(f"⚠️ Scraping initial: {e}")

    total = admin_count + external_count
    logger.info(f"✅ Bot prêt : {total} comptes ({admin_count} admin + {external_count} externes)")


def main():
    """Point d'entrée principal"""
    logger.info("🔄 Initialisation du bot...")

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

    logger.info("🔄 Démarrage du polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
