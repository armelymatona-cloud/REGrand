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
from config import BOT_TOKEN, AUTHORIZED_USERS, DEFAULT_API_ID, DEFAULT_API_HASH, SESSION_STRING
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

# Device models réalistes
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


# ========== GESTIONNAIRE DE COMPTES SIGNALEMENT (via /add) ==========
class ReportingAccounts:
    """
    Gère les comptes ajoutés via /add (comptes non-admin)
    Ces comptes sont utilisés pour le signalement en complément des comptes admin.
    """
    
    FILE_PATH = "reporting_accounts.json"
    
    def __init__(self):
        self.accounts = {}
        self.clients = {}
        self._load()
    
    def _load(self):
        try:
            if os.path.exists(self.FILE_PATH):
                with open(self.FILE_PATH, "r") as f:
                    self.accounts = json.load(f)
                logger.info(f"📂 {len(self.accounts)} comptes signalement chargés")
        except Exception as e:
            logger.error(f"Erreur chargement {self.FILE_PATH}: {e}")
            self.accounts = {}
    
    def _save(self):
        try:
            data = {}
            for phone, info in self.accounts.items():
                data[phone] = {
                    "session_string": info.get("session_string", ""),
                    "status": info.get("status", "inactive"),
                    "me_info": info.get("me_info", {})
                }
            with open(self.FILE_PATH, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Erreur sauvegarde {self.FILE_PATH}: {e}")
    
    def add(self, phone, session_string, me_info=None):
        self.accounts[phone] = {
            "session_string": session_string,
            "status": "active",
            "me_info": me_info or {}
        }
        self._save()
    
    def remove(self, phone):
        if phone in self.accounts:
            del self.accounts[phone]
        if phone in self.clients:
            try:
                client, _ = self.clients[phone]
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(client.disconnect())
                else:
                    loop.run_until_complete(client.disconnect())
            except:
                pass
            del self.clients[phone]
        self._save()
    
    async def connect_all(self):
        """Connecte tous les comptes signalement stockés"""
        connected = 0
        for phone, info in list(self.accounts.items()):
            if info.get("status") != "active" or not info.get("session_string"):
                continue
            try:
                client = create_telegram_client(info["session_string"])
                await client.connect()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    
                    # ⛔ VÉRIFICATION : Ne JAMAIS connecter un admin ici
                    if me.id in authorized_users:
                        logger.warning(f"⛔ Admin {me.id} ({phone}) détecté dans reporting_accounts ! Suppression...")
                        self.remove(phone)
                        continue
                    
                    self.clients[phone] = (client, me)
                    connected += 1
                    logger.info(f"✅ Compte signalement: {phone} ({me.first_name})")
                else:
                    logger.warning(f"⚠️ Session expirée: {phone}")
                    info["status"] = "expired"
                    self._save()
            except Exception as e:
                logger.error(f"❌ Erreur connexion {phone}: {e}")
        
        logger.info(f"📊 {connected}/{len(self.accounts)} comptes signalement actifs")
        return connected
    
    def get_active_clients(self):
        """Retourne la liste des (client, me) pour les comptes signalement"""
        return [(c, m) for c, m in self.clients.values()]


# Instanciation globale
reporting_accounts = ReportingAccounts()


# ========== FONCTIONS UTILITAIRES ==========

def generate_random_fingerprint():
    return {
        "device_model": random.choice(REAL_DEVICES),
        "system_version": random.choice(REAL_SYSTEM_VERSIONS),
        "app_version": random.choice(REAL_APP_VERSIONS),
        "lang_code": random.choice(REAL_LANG_CODES),
        "system_lang_code": "fr" if random.random() > 0.5 else "en",
    }


def create_telegram_client(session_string=None):
    """Crée un client Telethon avec empreinte réaliste"""
    fp = generate_random_fingerprint()
    
    if session_string:
        session = StringSession(session_string)
    else:
        session = StringSession()
    
    client = TelegramClient(
        session,
        DEFAULT_API_ID,
        DEFAULT_API_HASH,
        device_model=fp["device_model"],
        system_version=fp["system_version"],
        app_version=fp["app_version"],
        lang_code=fp["lang_code"],
        system_lang_code=fp["system_lang_code"],
        connection_retries=3,
        timeout=20,
    )
    return client


def auth_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in authorized_users:
            logger.warning(f"⛔ Accès refusé: {update.effective_user.id}")
            await update.message.reply_text("⛔ Non autorisé")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


# ========== COMMANDES ==========

@auth_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu d'aide"""
    admin_clients = await session_mgr.get_active_clients()
    reporting_clients = reporting_accounts.get_active_clients()
    total_reporting = len(admin_clients) + len(reporting_clients)
    
    msg = (
        f"🤖 **TELEGRAM REPORT BOT**\n\n"
        f"📱 Comptes signalement: {total_reporting} disponibles\n"
        f"   • Admins: {len(admin_clients)}\n"
        f"   • Externes: {len(reporting_clients)}\n"
        f"🔌 Proxies: {db.get_proxy_count()} en base\n\n"
        f"**Commandes:**\n"
        f"`/add +22501234567` - Ajouter compte externe\n"
        f"`/co 12345` - Code de vérification\n"
        f"`/cod2 mdp` - Code 2FA\n"
        f"`/status` - Statut général\n"
        f"`/702 @user` - Signaler (tous les comptes)\n"
        f"`/scrape` - Scraper des proxies\n"
        f"`/del +225...` - Supprimer un compte externe\n"
        f"`/reconnect` - Reconnecter tous les comptes\n\n"
        f"⚠️ Les admins du bot ne peuvent PAS être signalés."
    )
    await update.message.reply_text(msg, parse_mode='Markdown')


@auth_required
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ajoute un compte EXTERNE (non-admin) pour le signalement.
    Ces comptes s'ajoutent aux comptes admin pour /702.
    Les admins ne peuvent pas être ajoutés ici.
    """
    if not context.args:
        await update.message.reply_text("Usage: `/add +22501234567`", parse_mode='Markdown')
        return
    
    phone = context.args[0].strip()
    logger.info(f"📱 Ajout compte externe: {phone}")
    
    if not phone.startswith('+'):
        phone = '+' + phone
    
    if len(phone) < 10:
        await update.message.reply_text(
            f"❌ Numéro trop court: `{phone}`\nFormat: `+22501234567`",
            parse_mode='Markdown'
        )
        return
    
    msg = await update.message.reply_text(
        f"📱 Connexion de `{phone}`...\nPatientez...",
        parse_mode='Markdown'
    )
    
    try:
        client = create_telegram_client()
        await client.connect()
        
        is_auth = await client.is_user_authorized()
        
        if is_auth:
            me = await client.get_me()
            
            # ⛔ VÉRIFICATION : Ne JAMAIS ajouter un admin
            if me.id in authorized_users:
                await msg.edit_text(
                    f"⛔ **Ce compte est un ADMIN.**\n\n"
                    f"Les comptes administrateurs sont déjà disponibles "
                    f"pour le signalement via /702. Pas besoin de les ajouter.",
                    parse_mode='Markdown'
                )
                await client.disconnect()
                return
            
            session_string = client.session.save()
            
            reporting_accounts.add(phone, session_string, {
                "id": me.id,
                "first_name": me.first_name or "",
                "username": me.username or ""
            })
            reporting_accounts.clients[phone] = (client, me)
            
            await msg.edit_text(
                f"✅ **Compte externe ajouté !**\n"
                f"📱 `{phone}`\n"
                f"👤 {me.first_name or '?'} (@{me.username or 'inconnu'})\n\n"
                f"Il sera utilisé avec tes comptes admin pour /702.",
                parse_mode='Markdown'
            )
            return
        
        # Envoi du code
        sent = await client.send_code_request(phone)
        
        _pending[phone] = {
            'client': client,
            'phone_code_hash': sent.phone_code_hash,
            'user_id': update.effective_user.id,
            'phone': phone,
            'type': 'reporting'
        }
        
        await msg.edit_text(
            f"✅ **Code envoyé à** `{phone}`\n\n"
            f"📨 Utilise `/co CODE` (ex: `/co 12345`)",
            parse_mode='Markdown'
        )
        
    except PhoneNumberInvalidError:
        await msg.edit_text(f"❌ Numéro invalide: `{phone}`", parse_mode='Markdown')
    except PhoneNumberBannedError:
        await msg.edit_text(f"❌ `{phone}` est banni de Telegram", parse_mode='Markdown')
    except PhoneNumberFloodError:
        await msg.edit_text(f"❌ Trop de tentatives pour `{phone}`", parse_mode='Markdown')
    except FloodWaitError as e:
        await msg.edit_text(f"❌ Flood: attend {e.seconds}s", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Erreur add_account: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ **Erreur**: ```{str(e)[:300]}```\n\n"
            f"Vérifie:\n"
            f"1. Le format du numéro (+225...)\n"
            f"2. API_ID/API_HASH dans config.py\n"
            f"3. Que le compte Telegram existe",
            parse_mode='Markdown'
        )


@auth_required
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/co 12345"""
    if not context.args:
        await update.message.reply_text("Usage: `/co 12345`", parse_mode='Markdown')
        return
    
    code = context.args[0].strip()
    user_id = update.effective_user.id
    
    phone_to_verify = None
    pending_data = None
    for phone, data in list(_pending.items()):
        if data.get('user_id') == user_id and data.get('type') == 'reporting':
            phone_to_verify = phone
            pending_data = data
            break
    
    if not pending_data:
        await update.message.reply_text(
            "❌ Aucune connexion en attente.\nFais `/add +22501234567` d'abord.",
            parse_mode='Markdown'
        )
        return
    
    msg = await update.message.reply_text(
        f"🔄 Vérification de `{phone_to_verify}`...",
        parse_mode='Markdown'
    )
    
    try:
        client = pending_data['client']
        
        try:
            await client.sign_in(
                phone=phone_to_verify,
                code=code,
                phone_code_hash=pending_data['phone_code_hash']
            )
            
            me = await client.get_me()
            
            # ⛔ VÉRIFICATION ADMIN
            if me.id in authorized_users:
                await msg.edit_text(
                    f"⛔ **Compte ADMIN détecté !**\n"
                    f"`{me.first_name}` est un admin. Déjà disponible pour /702.",
                    parse_mode='Markdown'
                )
                await client.disconnect()
                if phone_to_verify in _pending:
                    del _pending[phone_to_verify]
                return
            
            session_string = client.session.save()
            
            reporting_accounts.add(phone_to_verify, session_string, {
                "id": me.id,
                "first_name": me.first_name or "",
                "username": me.username or ""
            })
            reporting_accounts.clients[phone_to_verify] = (client, me)
            
            if phone_to_verify in _pending:
                del _pending[phone_to_verify]
            
            await msg.edit_text(
                f"✅ **Compte externe connecté !**\n"
                f"📱 `{phone_to_verify}`\n"
                f"👤 {me.first_name or '?'} (@{me.username or 'inconnu'})\n\n"
                f"Il sera utilisé avec tes comptes admin pour /702.",
                parse_mode='Markdown'
            )
            
        except SessionPasswordNeededError:
            await msg.edit_text(
                f"🔐 **2FA requis**\nUtilise `/cod2 TON_MOT_DE_PASSE`",
                parse_mode='Markdown'
            )
        except PhoneCodeInvalidError:
            await msg.edit_text(f"❌ Code invalide. `/co CODE`", parse_mode='Markdown')
        except PhoneCodeExpiredError:
            if phone_to_verify in _pending:
                del _pending[phone_to_verify]
            await msg.edit_text(f"❌ Code expiré. Refais `/add +225...`", parse_mode='Markdown')
        except FloodWaitError as e:
            await msg.edit_text(f"❌ Flood: {e.seconds}s", parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Erreur: {str(e)[:200]}", parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Erreur verify_code: {e}", exc_info=True)
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}", parse_mode='Markdown')


@auth_required
async def verify_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cod2 motdepasse"""
    if not context.args:
        await update.message.reply_text("Usage: `/cod2 TON_MOT_DE_PASSE`", parse_mode='Markdown')
        return
    
    password = ' '.join(context.args)
    user_id = update.effective_user.id
    
    phone_to_verify = None
    pending_data = None
    for phone, data in list(_pending.items()):
        if data.get('user_id') == user_id and data.get('type') == 'reporting':
            phone_to_verify = phone
            pending_data = data
            break
    
    if not pending_data:
        await update.message.reply_text(
            "❌ Aucune connexion en attente.\nFais `/add +225...` d'abord.",
            parse_mode='Markdown'
        )
        return
    
    msg = await update.message.reply_text(f"🔄 Vérification 2FA...", parse_mode='Markdown')
    
    try:
        client = pending_data['client']
        await client.sign_in(password=password)
        
        me = await client.get_me()
        
        # ⛔ VÉRIFICATION ADMIN
        if me.id in authorized_users:
            await msg.edit_text(
                f"⛔ Compte ADMIN détecté ! Déjà disponible.",
                parse_mode='Markdown'
            )
            await client.disconnect()
            if phone_to_verify in _pending:
                del _pending[phone_to_verify]
            return
        
        session_string = client.session.save()
        
        reporting_accounts.add(phone_to_verify, session_string, {
            "id": me.id,
            "first_name": me.first_name or "",
            "username": me.username or ""
        })
        reporting_accounts.clients[phone_to_verify] = (client, me)
        
        if phone_to_verify in _pending:
            del _pending[phone_to_verify]
        
        await msg.edit_text(
            f"✅ **Compte externe connecté (2FA) !**\n"
            f"📱 `{phone_to_verify}`\n"
            f"👤 {me.first_name or '?'}",
            parse_mode='Markdown'
        )
        
    except PasswordHashInvalidError:
        await msg.edit_text("❌ Mot de passe 2FA incorrect.", parse_mode='Markdown')
    except FloodWaitError as e:
        await msg.edit_text(f"❌ Flood: {e.seconds}s", parse_mode='Markdown')
    except Exception as e:
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}", parse_mode='Markdown')


@auth_required
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le statut complet"""
    admin_clients = await session_mgr.get_active_clients()
    admin_count = len(admin_clients)
    reporting_clients_list = reporting_accounts.get_active_clients()
    reporting_connected = len(reporting_clients_list)
    reporting_count = len(reporting_accounts.accounts)
    total_reporting = admin_count + reporting_connected
    
    msg = f"**📊 Status**\n\n"
    msg += f"🤖 **Bot Admin:** ✅ Actif\n\n"
    msg += f"📱 **Comptes disponibles pour /702:** {total_reporting}\n\n"
    msg += f"**Comptes ADMIN** (connexion automatique):\n"
    msg += f"   • Connectés: {admin_count}\n"
    
    if admin_clients:
        for client, me in admin_clients[:10]:
            uname = f"(@{me.username})" if me.username else ""
            msg += f"   ✅ `{me.id}` {me.first_name or '?'} {uname}\n"
    
    msg += f"\n**Comptes EXTERNES** (ajoutés via /add):\n"
    msg += f"   • Enregistrés: {reporting_count}\n"
    msg += f"   • Connectés: {reporting_connected}\n"
    
    if reporting_clients_list:
        for phone, (client, me) in reporting_clients_list[:10]:
            uname = f"(@{me.username})" if me.username else ""
            msg += f"   ✅ `{phone}` {me.first_name or '?'} {uname}\n"
    
    msg += f"\n🔌 **Proxies:** {db.get_proxy_count()} en base\n\n"
    msg += f"⚠️ Les admins du bot ne peuvent JAMAIS être signalés."
    
    await update.message.reply_text(msg, parse_mode='Markdown')


@auth_required
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /702 @user
    Signale en UTILISANT TOUS LES COMPTES disponibles :
    - Comptes admin (ceux dans AUTHORIZED_USERS)
    - Comptes externes (ajoutés via /add)
    
    Les admins du bot ne peuvent PAS être la cible.
    """
    if not context.args:
        await update.message.reply_text("Usage: `/702 @username`", parse_mode='Markdown')
        return
    
    target_username = context.args[0].strip()
    target_clean = target_username.lstrip('@').lower()
    
    # ===== PROTECTION : Récupérer les infos des admins =====
    admin_ids = set(authorized_users)
    admin_usernames = set()
    
    for admin_id in admin_ids:
        try:
            chat = await context.bot.get_chat(admin_id)
            if chat.username:
                admin_usernames.add(chat.username.lower())
                admin_usernames.add(f"@{chat.username.lower()}")
        except:
            pass
    
    # Vérifier aussi via les comptes admin connectés
    admin_clients_check = await session_mgr.get_active_clients()
    for client, me in admin_clients_check:
        admin_ids.add(me.id)
        if me.username:
            admin_usernames.add(me.username.lower())
            admin_usernames.add(f"@{me.username.lower()}")
    
    # ⛔ VÉRIFICATION : La cible est-elle un admin ?
    if target_clean in admin_usernames or target_clean.replace('@', '') in admin_usernames:
        await update.message.reply_text(
            f"❌ **Signalement BLOQUÉ !**\n"
            f"`{target_username}` est un administrateur du bot.\n\n"
            f"Les administrateurs sont protégés et ne peuvent pas être signalés.",
            parse_mode='Markdown'
        )
        return
    
    # Vérification supplémentaire par ID via Telethon
    if admin_clients_check:
        try:
            client, _ = admin_clients_check[0]
            target_entity = await client.get_entity(target_username)
            if hasattr(target_entity, 'id') and target_entity.id in admin_ids:
                await update.message.reply_text(
                    f"❌ **Signalement BLOQUÉ !**\n"
                    f"Cette cible (ID: {target_entity.id}) est un administrateur.",
                    parse_mode='Markdown'
                )
                return
        except:
            pass
    
    # ===== RÉCUPÉRER TOUS LES COMPTES DISPONIBLES =====
    all_clients = []
    
    # 1. Comptes admin (via session_mgr)
    admin_clients = await session_mgr.get_active_clients()
    all_clients.extend(admin_clients)
    logger.info(f"👤 {len(admin_clients)} comptes admin disponibles")
    
    # 2. Comptes externes (via reporting_accounts)
    reporting_clients = reporting_accounts.get_active_clients()
    all_clients.extend(reporting_clients)
    logger.info(f"👤 {len(reporting_clients)} comptes externes disponibles")
    
    if len(all_clients) < 1:
        await update.message.reply_text(
            "⚠️ **Aucun compte disponible pour signaler.**\n\n"
            "Ajoute des comptes admin dans AUTHORIZED_USERS (config.py)\n"
            "ou ajoute des comptes externes avec `/add +22501234567`",
            parse_mode='Markdown'
        )
        return
    
    msg = await update.message.reply_text(
        f"🎯 Signalement de `{target_username}`\n"
        f"📱 {len(all_clients)} comptes (admin + externes)...",
        parse_mode='Markdown'
    )
    
    try:
        success = await reporter.coordinated_report(all_clients, target_username)
        
        db.add_target(target_username)
        db.increment_target_reports(target_username)
        
        admin_count = len(admin_clients)
        
        await msg.edit_text(
            f"✅ **Signalement terminé**\n"
            f"🎯 `{target_username}`\n"
            f"📊 {success}/{len(all_clients)} ont signalé\n"
            f"   • Admins: {min(success, admin_count)}/{admin_count}\n"
            f"   • Externes: {max(0, success - admin_count)}/{len(reporting_clients)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erreur report: {e}", exc_info=True)
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}", parse_mode='Markdown')


@auth_required
async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/del +225XXXXXXXX - Supprime un compte externe"""
    if not context.args:
        await update.message.reply_text("Usage: `/del +225XXXXXXXX`", parse_mode='Markdown')
        return
    
    phone = context.args[0].strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    
    if phone in reporting_accounts.accounts:
        reporting_accounts.remove(phone)
        await update.message.reply_text(
            f"🗑️ `{phone}` retiré des comptes externes.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"❌ `{phone}` n'est pas dans les comptes externes.\n"
            f"Liste: {', '.join(reporting_accounts.accounts.keys()) or 'aucun'}",
            parse_mode='Markdown'
        )


@auth_required
async def scrape_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scrape"""
    msg = await update.message.reply_text("🕷️ Scraping des proxies...")
    count = await proxy_scraper.scrape_and_store()
    valid = db.get_proxy_count()
    await msg.edit_text(
        f"✅ **Scraping terminé**\n"
        f"📥 {count} nouveaux proxies\n"
        f"🔌 Total: {valid}",
        parse_mode='Markdown'
    )


@auth_required
async def reconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reconnect - Reconnecte tous les comptes"""
    msg = await update.message.reply_text("🔄 Reconnexion de tous les comptes...")
    
    # Reconnecter les comptes admin
    await session_mgr.disconnect_all()
    admin_count = await session_mgr.load_all_active_accounts()
    if admin_count is None:
        admin_count = 0
    
    # Reconnecter les comptes externes
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
    
    total = admin_count + external_count
    
    await msg.edit_text(
        f"✅ **Reconnexion terminée**\n"
        f"📱 {total} comptes reconnectés\n"
        f"   • Admins: {admin_count}\n"
        f"   • Externes: {external_count}",
        parse_mode='Markdown'
    )


# ========== INITIALISATION ==========

async def post_init(app: Application):
    """Fonction exécutée après le démarrage du bot"""
    logger.info("🚀 Démarrage du bot...")
    
    os.makedirs("sessions", exist_ok=True)
    
    # 1. Charger les comptes admin (via session_mgr)
    logger.info("👤 Chargement des comptes admin...")
    admin_count = await session_mgr.load_all_active_accounts()
    
    # ✅ SÉCURISÉ : Si None, on met 0
    if admin_count is None:
        admin_count = 0
        logger.warning("⚠️ load_all_active_accounts a retourné None, forcé à 0")
    
    logger.info(f"✅ {admin_count} comptes admin chargés")
    
    # 2. Charger les comptes externes (via reporting_accounts)
    logger.info("👤 Chargement des comptes externes...")
    external_count = await reporting_accounts.connect_all()
    
    # ✅ SÉCURISÉ : Si None, on met 0
    if external_count is None:
        external_count = 0
        logger.warning("⚠️ connect_all a retourné None, forcé à 0")
    
    logger.info(f"✅ {external_count} comptes externes chargés")
    
    # 3. Scraper les proxies si aucun en base
    if db.get_proxy_count() == 0:
        logger.info("🔌 Aucun proxy, scraping...")
        try:
            count = await proxy_scraper.scrape_and_store()
            logger.info(f"🔌 {count} proxies scrapés")
        except Exception as e:
            logger.warning(f"⚠️ Scraping proxies: {e}")
    
    total = admin_count + external_count
    logger.info(f"✅ Bot prêt: {total} comptes ({admin_count} admin + {external_count} externes), {db.get_proxy_count()} proxies")


def main():
    """Point d'entrée principal"""
    logger.info("🔄 Initialisation du bot...")
    
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Enregistrer les commandes
    app.add_handler(CommandHandler("start", start))
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
