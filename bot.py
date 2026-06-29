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


# ========== GESTIONNAIRE DE COMPTES EXTERNES ==========
class ReportingAccounts:
    """Gère les comptes ajoutés via /add"""
    
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
                logger.info(f"📂 {len(self.accounts)} comptes externes chargés")
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
        connected = 0
        for phone, info in list(self.accounts.items()):
            if info.get("status") != "active" or not info.get("session_string"):
                continue
            try:
                client = create_telegram_client(info["session_string"])
                await client.connect()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    if me.id in authorized_users:
                        logger.warning(f"⛔ Admin {me.id} ({phone}) détecté, suppression...")
                        self.remove(phone)
                        continue
                    self.clients[phone] = (client, me)
                    connected += 1
                    logger.info(f"✅ Compte externe: {phone} ({me.first_name})")
                else:
                    logger.warning(f"⚠️ Session expirée: {phone}")
                    info["status"] = "expired"
                    self._save()
            except Exception as e:
                logger.error(f"❌ Erreur connexion {phone}: {e}")
        
        logger.info(f"📊 {connected}/{len(self.accounts)} comptes externes actifs")
        return connected
    
    def get_active_clients(self):
        return [(c, m) for c, m in self.clients.values()]


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
    admin_clients = await session_mgr.get_active_clients()
    reporting_clients = reporting_accounts.get_active_clients()
    total_reporting = len(admin_clients) + len(reporting_clients)
    
    msg = (
        f"🤖 **TELEGRAM REPORT BOT**\n\n"
        f"📱 Comptes disponibles: {total_reporting}\n"
        f"   • Admins: {len(admin_clients)}\n"
        f"   • Externes: {len(reporting_clients)}\n"
        f"🔌 Proxies: {db.get_proxy_count()}\n\n"
        f"**Commandes:**\n"
        f"`/add +225XXXXXXXX` - Ajouter compte externe\n"
        f"`/co 12345` - Code de vérification\n"
        f"`/cod2 mdp` - Code 2FA\n"
        f"`/status` - Statut\n"
        f"`/702 @user` - Signaler\n"
        f"`/scrape` - Scraper proxies\n"
        f"`/del +225...` - Supprimer externe\n"
        f"`/reconnect` - Reconnecter\n\n"
        f"⚠️ Les admins ne peuvent PAS être signalés."
    )
    await update.message.reply_text(msg, parse_mode='Markdown')


@auth_required
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ajoute un compte EXTERNE (non-admin)
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
            f"❌ Numéro trop court: `{phone}`",
            parse_mode='Markdown'
        )
        return
    
    msg = await update.message.reply_text(
        f"📱 Connexion de `{phone}`...",
        parse_mode='Markdown'
    )
    
    try:
        client = create_telegram_client()
        await client.connect()
        
        is_auth = await client.is_user_authorized()
        
        if is_auth:
            me = await client.get_me()
            
            if me.id in authorized_users:
                await msg.edit_text(
                    f"⛔ Ce compte est un ADMIN. Déjà disponible.",
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
                f"👤 {me.first_name or '?'}",
                parse_mode='Markdown'
            )
            return
        
        # Envoi du code
        sent = await client.send_code_request(phone)
        
        # Stocker le pending
        _pending[phone] = {
            'client': client,
            'phone_code_hash': sent.phone_code_hash,
            'user_id': update.effective_user.id,
            'phone': phone,
            'type': 'reporting'
        }
        
        # PERSISTER DANS LA DB POUR RÉCUPÉRATION
        db.set_pending_login(
            update.effective_user.id,
            phone,
            DEFAULT_API_ID,
            DEFAULT_API_HASH,
            "code_sent",
            sent.phone_code_hash
        )
        
        await msg.edit_text(
            f"✅ **Code envoyé à** `{phone}`\n\n"
            f"📨 Utilise `/co CODE` (ex: `/co 12345`)",
            parse_mode='Markdown'
        )
        
    except PhoneNumberInvalidError:
        await msg.edit_text(f"❌ Numéro invalide: `{phone}`", parse_mode='Markdown')
    except PhoneNumberBannedError:
        await msg.edit_text(f"❌ `{phone}` est banni", parse_mode='Markdown')
    except PhoneNumberFloodError:
        await msg.edit_text(f"❌ Trop de tentatives", parse_mode='Markdown')
    except FloodWaitError as e:
        await msg.edit_text(f"❌ Flood: attend {e.seconds}s", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Erreur: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ **Erreur**: ```{str(e)[:300]}```",
            parse_mode='Markdown'
        )


@auth_required
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /co 12345
    Vérifie le code reçu.
    Gère le cas où le client s'est déconnecté entre temps.
    """
    if not context.args:
        await update.message.reply_text("Usage: `/co 12345`", parse_mode='Markdown')
        return
    
    code = context.args[0].strip()
    user_id = update.effective_user.id
    
    # ===== ÉTAPE 1: Chercher dans _pending (mémoire) =====
    phone_to_verify = None
    pending_data = None
    
    for phone, data in list(_pending.items()):
        if data.get('user_id') == user_id and data.get('type') == 'reporting':
            phone_to_verify = phone
            pending_data = data
            break
    
    # ===== ÉTAPE 2: Si pas en mémoire, restaurer depuis la DB =====
    if not pending_data:
        pending_db = db.get_pending_login(user_id)
        if pending_db:
            phone_to_verify = pending_db['phone']
            logger.info(f"🔄 Restauration depuis DB pour {phone_to_verify}")
            
            try:
                # Créer un NOUVEAU client
                client = create_telegram_client()
                await client.connect()
                
                pending_data = {
                    'client': client,
                    'phone_code_hash': pending_db.get('phone_code_hash', ''),
                    'user_id': user_id,
                    'phone': phone_to_verify,
                    'type': 'reporting'
                }
                
                # Le remettre en mémoire
                _pending[phone_to_verify] = pending_data
                
            except Exception as e:
                logger.error(f"❌ Erreur restauration pending: {e}")
                await update.message.reply_text(
                    "❌ Impossible de restaurer la connexion.\n"
                    "Fais `/add +225...` à nouveau.",
                    parse_mode='Markdown'
                )
                return
        else:
            await update.message.reply_text(
                "❌ Aucune connexion en attente.\nFais `/add +225...` d'abord.",
                parse_mode='Markdown'
            )
            return
    
    if not pending_data:
        await update.message.reply_text(
            "❌ Aucune connexion en attente.",
            parse_mode='Markdown'
        )
        return
    
    msg = await update.message.reply_text(
        f"🔄 Vérification de `{phone_to_verify}`...",
        parse_mode='Markdown'
    )
    
    try:
        client = pending_data['client']
        
        # ===== ÉTAPE 3: Vérifier si le client est connecté =====
        if not client.is_connected():
            logger.info(f"🔄 Reconnexion du client pour {phone_to_verify}...")
            try:
                await client.connect()
                logger.info(f"✅ Client reconnecté pour {phone_to_verify}")
            except Exception as e:
                logger.error(f"❌ Échec reconnexion: {e}")
                # Si la reconnexion échoue, créer un nouveau client
                try:
                    logger.info("🔄 Création d'un nouveau client...")
                    new_client = create_telegram_client()
                    await new_client.connect()
                    await new_client.send_code_request(phone_to_verify)
                    await msg.edit_text(
                        f"❌ La session a expiré. Un nouveau code a été envoyé à `{phone_to_verify}`.\n"
                        f"Utilise `/co NOUVEAU_CODE`",
                        parse_mode='Markdown'
                    )
                    return
                except Exception as e2:
                    await msg.edit_text(
                        f"❌ Erreur: ```{str(e2)[:200]}```\n"
                        f"Refais `/add +225...`",
                        parse_mode='Markdown'
                    )
                    return
        
        # ===== ÉTAPE 4: Tenter la connexion =====
        try:
            await client.sign_in(
                phone=phone_to_verify,
                code=code,
                phone_code_hash=pending_data['phone_code_hash']
            )
            
            # SUCCÈS !
            me = await client.get_me()
            
            # Vérifier si c'est un admin
            if me.id in authorized_users:
                await msg.edit_text(
                    f"⛔ Compte ADMIN détecté. Déjà disponible.",
                    parse_mode='Markdown'
                )
                await client.disconnect()
                if phone_to_verify in _pending:
                    del _pending[phone_to_verify]
                db.remove_pending_login(user_id)
                return
            
            # Sauvegarder la session
            session_string = client.session.save()
            reporting_accounts.add(phone_to_verify, session_string, {
                "id": me.id,
                "first_name": me.first_name or "",
                "username": me.username or ""
            })
            reporting_accounts.clients[phone_to_verify] = (client, me)
            
            # Nettoyer
            if phone_to_verify in _pending:
                del _pending[phone_to_verify]
            db.remove_pending_login(user_id)
            
            await msg.edit_text(
                f"✅ **Compte externe connecté !**\n"
                f"📱 `{phone_to_verify}`\n"
                f"👤 {me.first_name or '?'}\n\n"
                f"Prêt pour /702",
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
            await msg.edit_text(
                f"❌ Code expiré.\n\n"
                f"**Raison :** Telegram bloque car le code a été partagé "
                f"depuis ton compte principal.\n\n"
                f"**Solution :** Utilise un **autre compte Telegram** "
                f"avec `/add +AUTRE_NUMERO`",
                parse_mode='Markdown'
            )
            if phone_to_verify in _pending:
                del _pending[phone_to_verify]
            db.remove_pending_login(user_id)
        except FloodWaitError as e:
            await msg.edit_text(f"❌ Flood: {e.seconds}s", parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Erreur: {str(e)[:200]}", parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"❌ Erreur verify_code: {e}", exc_info=True)
        await msg.edit_text(f"❌ Erreur générale: {str(e)[:200]}", parse_mode='Markdown')


@auth_required
async def verify_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cod2 motdepasse"""
    if not context.args:
        await update.message.reply_text("Usage: `/cod2 TON_MOT_DE_PASSE`", parse_mode='Markdown')
        return
    
    password = ' '.join(context.args)
    user_id = update.effective_user.id
    
    # Chercher dans _pending
    phone_to_verify = None
    pending_data = None
    for phone, data in list(_pending.items()):
        if data.get('user_id') == user_id and data.get('type') == 'reporting':
            phone_to_verify = phone
            pending_data = data
            break
    
    # Fallback DB
    if not pending_data:
        pending_db = db.get_pending_login(user_id)
        if pending_db:
            phone_to_verify = pending_db['phone']
            try:
                client = create_telegram_client()
                await client.connect()
                pending_data = {
                    'client': client,
                    'phone_code_hash': pending_db.get('phone_code_hash', ''),
                    'user_id': user_id,
                    'phone': phone_to_verify,
                    'type': 'reporting'
                }
                _pending[phone_to_verify] = pending_data
            except Exception as e:
                logger.error(f"Erreur restauration 2FA: {e}")
    
    if not pending_data:
        await update.message.reply_text(
            "❌ Aucune connexion en attente.",
            parse_mode='Markdown'
        )
        return
    
    msg = await update.message.reply_text(f"🔄 Vérification 2FA...", parse_mode='Markdown')
    
    try:
        client = pending_data['client']
        
        if not client.is_connected():
            await client.connect()
        
        await client.sign_in(password=password)
        
        me = await client.get_me()
        
        if me.id in authorized_users:
            await msg.edit_text(f"⛔ Compte ADMIN détecté !", parse_mode='Markdown')
            await client.disconnect()
            if phone_to_verify in _pending:
                del _pending[phone_to_verify]
            db.remove_pending_login(user_id)
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
        db.remove_pending_login(user_id)
        
        await msg.edit_text(
            f"✅ **Compte externe connecté (2FA) !**\n"
            f"📱 `{phone_to_verify}`",
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
    admin_clients = await session_mgr.get_active_clients()
    admin_count = len(admin_clients)
    reporting_clients = reporting_accounts.get_active_clients()
    reporting_connected = len(reporting_clients)
    reporting_count = len(reporting_accounts.accounts)
    total = admin_count + reporting_connected
    
    msg = f"**📊 Status**\n\n"
    msg += f"📱 Total pour /702: {total}\n\n"
    msg += f"**ADMINS:** {admin_count}\n"
    
    for client, me in admin_clients[:5]:
        uname = f"(@{me.username})" if me.username else ""
        msg += f"✅ `{me.id}` {me.first_name or '?'} {uname}\n"
    
    msg += f"\n**EXTERNES:** {reporting_connected}/{reporting_count}\n"
    
    for phone, (client, me) in reporting_clients[:5]:
        uname = f"(@{me.username})" if me.username else ""
        msg += f"✅ `{phone}` {me.first_name or '?'} {uname}\n"
    
    msg += f"\n🔌 Proxies: {db.get_proxy_count()}"
    
    await update.message.reply_text(msg, parse_mode='Markdown')


@auth_required
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/702 @user"""
    if not context.args:
        await update.message.reply_text("Usage: `/702 @username`", parse_mode='Markdown')
        return
    
    target_username = context.args[0].strip()
    target_clean = target_username.lstrip('@').lower()
    
    # Protection admin
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
    
    admin_clients_check = await session_mgr.get_active_clients()
    for client, me in admin_clients_check:
        admin_ids.add(me.id)
        if me.username:
            admin_usernames.add(me.username.lower())
            admin_usernames.add(f"@{me.username.lower()}")
    
    if target_clean in admin_usernames or target_clean.replace('@', '') in admin_usernames:
        await update.message.reply_text(
            f"❌ `{target_username}` est un admin. Bloqué.",
            parse_mode='Markdown'
        )
        return
    
    # Récupérer tous les comptes
    all_clients = []
    admin_clients = await session_mgr.get_active_clients()
    all_clients.extend(admin_clients)
    reporting_clients = reporting_accounts.get_active_clients()
    all_clients.extend(reporting_clients)
    
    if len(all_clients) < 1:
        await update.message.reply_text("⚠️ Aucun compte disponible.", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(
        f"🎯 Signalement de `{target_username}` ({len(all_clients)} comptes)...",
        parse_mode='Markdown'
    )
    
    try:
        success = await reporter.coordinated_report(all_clients, target_username)
        db.add_target(target_username)
        db.increment_target_reports(target_username)
        
        await msg.edit_text(
            f"✅ **Terminé**\n🎯 `{target_username}`\n📊 {success}/{len(all_clients)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}", parse_mode='Markdown')


@auth_required
async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/del +225XXXXXXXX"""
    if not context.args:
        await update.message.reply_text("Usage: `/del +225XXXXXXXX`", parse_mode='Markdown')
        return
    
    phone = context.args[0].strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    
    if phone in reporting_accounts.accounts:
        reporting_accounts.remove(phone)
        await update.message.reply_text(f"🗑️ `{phone}` retiré.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ `{phone}` introuvable.", parse_mode='Markdown')


@auth_required
async def scrape_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/scrape"""
    msg = await update.message.reply_text("🕷️ Scraping...")
    count = await proxy_scraper.scrape_and_store()
    valid = db.get_proxy_count()
    await msg.edit_text(f"✅ {count} nouveaux. Total: {valid}", parse_mode='Markdown')


@auth_required
async def reconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reconnect"""
    msg = await update.message.reply_text("🔄 Reconnexion...")
    
    await session_mgr.disconnect_all()
    admin_count = await session_mgr.load_all_active_accounts() or 0
    
    for phone in list(reporting_accounts.clients.keys()):
        try:
            await reporting_accounts.clients[phone][0].disconnect()
        except:
            pass
    reporting_accounts.clients.clear()
    external_count = await reporting_accounts.connect_all() or 0
    
    await msg.edit_text(
        f"✅ {admin_count + external_count} comptes reconnectés",
        parse_mode='Markdown'
    )


# ========== INITIALISATION ==========

async def post_init(app: Application):
    logger.info("🚀 Démarrage du bot...")
    os.makedirs("sessions", exist_ok=True)
    
    # Compte admin
    admin_count = 0
    if SESSION_STRING:
        try:
            logger.info("👤 Connexion admin via SESSION_STRING...")
            client = create_telegram_client(SESSION_STRING)
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                logger.info(f"✅ Admin: {me.first_name} (ID: {me.id})")
                if me.id not in authorized_users:
                    authorized_users.add(me.id)
                session_mgr.add_client_sync(f"admin_{me.id}", client, me)
                admin_count = 1
            else:
                logger.error("❌ SESSION_STRING expirée")
        except Exception as e:
            logger.error(f"❌ Erreur admin: {e}")
            admin_count = await session_mgr.load_all_active_accounts() or 0
    
    # Comptes externes
    external_count = await reporting_accounts.connect_all() or 0
    
    # Proxies
    if db.get_proxy_count() == 0:
        logger.info("🔌 Scraping proxies...")
        try:
            await proxy_scraper.scrape_and_store()
        except Exception as e:
            logger.warning(f"⚠️ Scraping: {e}")
    
    logger.info(f"✅ Bot prêt: {admin_count + external_count} comptes")


def main():
    logger.info("🔄 Initialisation...")
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
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
