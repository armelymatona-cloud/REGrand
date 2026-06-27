import asyncio
import logging
import os
import sys
import random
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telethon import TelegramClient
from telethon.errors import *
from telethon.sessions import StringSession
from config import BOT_TOKEN, AUTHORIZED_USERS, DEFAULT_API_ID, DEFAULT_API_HASH, SESSION_STRING
from database import Database
from session_mgr import SessionManager
from reporter import Reporter
from proxy_scraper import ProxyScraper

# Remplacez l'ancienne logique par celle-ci :
try:
    with open(".session", "r") as f:
        session_str = f.read().strip()
    
    # Création du client avec le contenu du fichier
    client = TelegramClient(StringSession(session_str), DEFAULT_API_ID, DEFAULT_API_HASH)
except FileNotFoundError:
    print("❌ ERREUR : Le fichier .session est introuvable !")
    
# LOGS DÉTAILLÉS
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log')
    ]
)
logger = logging.getLogger(__name__)

db = Database()
session_mgr = SessionManager(db)
reporter = Reporter(db)
proxy_scraper = ProxyScraper(db)

authorized_users = set(AUTHORIZED_USERS)
_pending = {}

# Device models réalistes pour éviter le flag Telegram
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

# Langues réalistes
REAL_LANG_CODES = ["fr", "en", "fr-FR", "en-US"]
REAL_SYSTEM_VERSIONS = [
    "Android 14",
    "Android 13",
    "iOS 18.0",
    "iOS 17.5",
    "Android 12",
]
REAL_APP_VERSIONS = [
    "10.14.5",
    "10.14.4",
    "10.13.3",
    "10.12.8",
    "11.0.0",
]

def auth_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in authorized_users:
            logger.warning(f"Utilisateur non authorisé: {update.effective_user.id}")
            await update.message.reply_text("⛔ Non authorisé")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def generate_random_fingerprint():
    """Génère une empreinte aléatoire réaliste pour chaque connexion"""
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
        connection_retries=5,
        timeout=30,
    )
    return client

@auth_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_active_accounts()
    proxies = db.get_proxy_count()
    msg = (
        f"🤖 **TELEGRAM PURGE BOT**\n\n"
        f"📱 Comptes: {len(session_mgr.clients)}/{len(accounts)} actifs\n"
        f"🔌 Proxies: {proxies} en base\n\n"
        f"**Commandes:**\n"
        f"`/add +22501234567` - Ajouter un compte\n"
        f"`/co 12345` - Code de vérification\n"
        f"`/cod2 mdp` - Code 2FA\n"
        f"`/status` - Statut\n"
        f"`/702 @user` - Signaler\n"
        f"`/scrape` - Scraper proxies\n"
        f"`/del +225...` - Supprimer\n"
        f"`/reconnect` - Reconnecter"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

@auth_required
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/add +XX123456789` (remplacez XX par l'indicatif du pays)", parse_mode='Markdown')
        return

    phone = context.args[0]
    logger.info(f"📱 Tentative d'ajout: {phone}")

    # Nettoyage automatique du numéro
    phone = phone.strip()
    if not phone.startswith('+'):
        phone = '+' + phone

    # Vérifier format
    if len(phone) < 10:
        await update.message.reply_text(f"❌ Numéro trop court: `{phone}`\nFormat: `+XX123456789` (remplacez XX par l'indicatif du pays)", parse_mode='Markdown')
        return

    msg = await update.message.reply_text(f"📱 Connexion de `{phone}`...\nPatientez...", parse_mode='Markdown')

    try:
        logger.debug(f"Création du client Telethon pour {phone}")
        
        # Créer client Telethon avec empreinte réaliste
        client = create_telegram_client()
        
        logger.debug("Connexion au DC Telegram...")
        await client.connect()
        
        logger.debug(f"Vérification autorisation pour {phone}...")
        is_auth = await client.is_user_authorized()
        logger.debug(f"is_user_authorized: {is_auth}")
        
        if is_auth:
            # Déjà connecté - sauvegarder immédiatement la session
            session_string = client.session.save()
            db.update_account_session(phone, session_string)
            db.update_account_status(phone, 'active')
            
            # Backup fichier
            _save_session_file(phone, session_string)
            
            # Ajouter au session manager
            await session_mgr.add_client(phone, client)
            
            await msg.edit_text(f"ℹ️ `{phone}` déjà connecté !", parse_mode='Markdown')
            return
        
        logger.debug(f"Envoi du code à {phone}...")
        sent = await client.send_code_request(phone)
        logger.debug(f"Code envoyé! phone_code_hash: {sent.phone_code_hash}")
        
        # Stocker en mémoire
        _pending[phone] = {
            'client': client,
            'phone_code_hash': sent.phone_code_hash,
            'user_id': update.effective_user.id,
            'phone': phone
        }
        
        # Persister en DB pour récupération après reboot
        db.add_account(phone, DEFAULT_API_ID, DEFAULT_API_HASH)
        db.set_pending_login(
            update.effective_user.id,
            phone,
            DEFAULT_API_ID,
            DEFAULT_API_HASH,
            "code_sent",
            sent.phone_code_hash  # ← Ajoute ce paramètre à ta méthode DB
        )
        
        await msg.edit_text(
            f"✅ **Code envoyé à** `{phone}`\n\n"
            f"📨 Vérifie tes SMS sur ton téléphone\n"
            f"📝 Utilise `/co CODE` (ex: `/co 12345`)\n\n"
            f"📱 Empreinte: `{client._device_model.split()[-1]}`",
            parse_mode='Markdown'
        )
        logger.info(f"✅ Code envoyé avec succès à {phone}")
        
    except PhoneNumber:
    print("Numéro invalide")
    
@auth_required
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/co 12345"""
    if not context.args:
        await update.message.reply_text("Usage: `/co 12345`", parse_mode='Markdown')
        return
    
    code = context.args[0].strip()
    user_id = update.effective_user.id
    
    logger.info(f"Vérification code pour user {user_id}: {code}")
    
    # Chercher le pending en mémoire d'abord
    phone_to_verify = None
    pending_data = None
    for phone, data in list(_pending.items()):
        if data.get('user_id') == user_id:
            phone_to_verify = phone
            pending_data = data
            break
    
    # Si pas en mémoire, essayer de restaurer depuis la DB
    if not pending_data:
        pending_db = db.get_pending_login(user_id)
        if pending_db:
            phone_to_verify = pending_db['phone']
            logger.info(f"Restauration pending depuis DB pour {phone_to_verify}")
            try:
                client = create_telegram_client()
                await client.connect()
                _pending[phone_to_verify] = {
                    'client': client,
                    'phone_code_hash': pending_db['phone_code_hash'],
                    'user_id': user_id,
                    'phone': phone_to_verify
                }
                pending_data = _pending[phone_to_verify]
            except Exception as e:
                logger.error(f"Erreur restauration pending: {e}")
                await update.message.reply_text(
                    "❌ Aucune connexion en attente.\n"
                    "Fais `/add +22501234567` d'abord.",
                    parse_mode='Markdown'
                )
                return
        else:
            await update.message.reply_text(
                "❌ Aucune connexion en attente.\n"
                "Fais `/add +22501234567` d'abord.",
                parse_mode='Markdown'
            )
            return
    
    msg = await update.message.reply_text(f"🔄 Vérification de `{phone_to_verify}`...", parse_mode='Markdown')
    
    try:
        client = pending_data['client']
        
        logger.debug(f"Tentative sign_in pour {phone_to_verify} avec code {code}...")
        
        try:
            await client.sign_in(
                phone=phone_to_verify,
                code=code,
                phone_code_hash=pending_data['phone_code_hash']
            )
            
            # ✅ Succès !
            logger.info(f"✅ {phone_to_verify} connecté avec succès!")
            session_string = client.session.save()
            
            # Sauvegarder session partout
            db.update_account_session(phone_to_verify, session_string)
            db.update_account_status(phone_to_verify, 'active')
            db.remove_pending_login(user_id)
            _save_session_file(phone_to_verify, session_string)
            
            # Ajouter au session manager
            await session_mgr.add_client(phone_to_verify, client)
            
            # Nettoyer pending
            if phone_to_verify in _pending:
                del _pending[phone_to_verify]
            
            await msg.edit_text(
                f"✅ **Compte connecté !**\n📱 `{phone_to_verify}`\n\n"
                f"Tu peux maintenant signaler avec `/702 @cible`",
                parse_mode='Markdown'
            )
            
        except SessionPasswordNeededError:
            logger.info(f"2FA requis pour {phone_to_verify}")
            await msg.edit_text(
                f"🔐 **Code 2FA requis**\n\n"
                f"Ce compte a l'authentification à deux facteurs.\n"
                f"Utilise `/cod2 TON_MOT_DE_PASSE`",
                parse_mode='Markdown'
            )
        except PhoneCodeInvalidError:
            logger.warning(f"Code invalide pour {phone_to_verify}")
            await msg.edit_text(
                f"❌ Code invalide.\n"
                f"Vérifie le SMS et réessaie: `/co CODE`",
                parse_mode='Markdown'
            )
        except PhoneCodeExpiredError:
            logger.warning(f"Code expiré pour {phone_to_verify}")
            if phone_to_verify in _pending:
                del _pending[phone_to_verify]
            await msg.edit_text(
                f"❌ Code expiré.\n"
                f"Refais `/add +225...` pour un nouveau code.",
                parse_mode='Markdown'
            )
        except FloodWaitError as e:
            await msg.edit_text(f"❌ Flood: {e.seconds}s")
        except Exception as e:
            logger.error(f"Erreur sign_in: {e}", exc_info=True)
            await msg.edit_text(f"❌ Erreur: {str(e)[:200]}")
            
    except Exception as e:
        logger.error(f"Erreur verify_code: {e}", exc_info=True)
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}")

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
        if data.get('user_id') == user_id:
            phone_to_verify = phone
            pending_data = data
            break
    
    # Restauration depuis DB si nécessaire
    if not pending_data:
        pending_db = db.get_pending_login(user_id)
        if pending_db:
            phone_to_verify = pending_db['phone']
            try:
                client = create_telegram_client()
                await client.connect()
                _pending[phone_to_verify] = {
                    'client': client,
                    'phone_code_hash': pending_db['phone_code_hash'],
                    'user_id': user_id,
                    'phone': phone_to_verify
                }
                pending_data = _pending[phone_to_verify]
            except Exception as e:
                logger.error(f"Erreur restauration pending 2FA: {e}")
    
    if not pending_data:
        await update.message.reply_text("❌ Aucune connexion en attente.", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(f"🔄 Vérification 2FA de `{phone_to_verify}`...", parse_mode='Markdown')
    
    try:
        client = pending_data['client']
        await client.sign_in(password=password)
        
        # ✅ Succès !
        session_string = client.session.save()
        
        # Sauvegarder partout
        db.update_account_session(phone_to_verify, session_string)
        db.update_account_status(phone_to_verify, 'active')
        db.remove_pending_login(user_id)
        _save_session_file(phone_to_verify, session_string)
        
        # Ajouter au session manager
        await session_mgr.add_client(phone_to_verify, client)
        
        if phone_to_verify in _pending:
            del _pending[phone_to_verify]
        
        await msg.edit_text(
            f"✅ **Compte connecté (2FA) !**\n📱 `{phone_to_verify}`",
            parse_mode='Markdown'
        )
        
    except PasswordHashInvalidError:
        await msg.edit_text("❌ Mot de passe 2FA incorrect.", parse_mode='Markdown')
    except FloodWaitError as e:
        await msg.edit_text(f"❌ Flood: {e.seconds}s")
    except Exception as e:
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}")

@auth_required
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_all_accounts()
    active_accounts = db.get_active_accounts()
    
    msg = f"**📊 Status**\n\n"
    msg += f"📱 Total: {len(accounts)}\n"
    msg += f"✅ Connectés: {len(session_mgr.clients)}/{len(active_accounts)}\n"
    msg += f"🔌 Proxies: {db.get_proxy_count()}\n"
    msg += f"💾 Sessions backup: {len(os.listdir('sessions')) if os.path.exists('sessions') else 0}\n\n"
    
    if session_mgr.clients:
        msg += "**Actifs:**\n"
        count = 0
        for phone in list(session_mgr.clients.keys()):
            if count >= 10:
                msg += f"...+{len(session_mgr.clients)-10}\n"
                break
            try:
                client, _ = session_mgr.clients[phone]
                if hasattr(client, 'get_me'):
                    me = await client.get_me()
                    name = f"{me.first_name or ''}".strip() or "?"
                else:
                    name = "?"
                msg += f"✅ `{phone}` {name}\n"
            except:
                msg += f"❌ `{phone}`\n"
            count += 1
    
    await update.message.reply_text(msg, parse_mode='Markdown')

@auth_required
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/702 @user"""
    if not context.args:
        await update.message.reply_text("Usage: `/702 @username`", parse_mode='Markdown')
        return
    
    target = context.args[0]
    clients = await session_mgr.get_active_clients()
    
    if len(clients) < 1:
        await update.message.reply_text("⚠️ Ajoute au moins 1 compte avec `/add`", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(
        f"🎯 Signalement de `{target}` ({len(clients)} comptes)...",
        parse_mode='Markdown'
    )
    
    try:
        success = await reporter.coordinated_report(clients, target)
        db.add_target(target)
        db.increment_target_reports(target)
        
        await msg.edit_text(
            f"✅ **Terminé**\n🎯 `{target}`\n📊 {success}/{len(clients)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}", parse_mode='Markdown')

@auth_required
async def scrape_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🕷️ Scraping des proxies...")
    count = await proxy_scraper.scrape_and_store()
    valid = db.get_proxy_count()
    await msg.edit_text(
        f"✅ **Scraping terminé**\n"
        f"📥 {count} nouveaux proxies\n"
        f"🔌 Total en base: {valid}",
        parse_mode='Markdown'
    )

@auth_required
async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/del +225XXXXXXXX`", parse_mode='Markdown')
        return
    phone = context.args[0]
    if not phone.startswith('+'):
        phone = '+' + phone
    
    # Déconnecter et supprimer
    await session_mgr.disconnect_account(phone)
    db.remove_account(phone)
    
    # Supprimer le fichier de session backup
    _remove_session_file(phone)
    
    await update.message.reply_text(f"🗑️ `{phone}` supprimé", parse_mode='Markdown')

@auth_required
async def reconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Reconnexion de tous les comptes...")
    await session_mgr.disconnect_all()
    await session_mgr.load_all_active_accounts()
    accounts = db.get_active_accounts()
    await msg.edit_text(
        f"✅ **Reconnexion terminée**\n"
        f"📱 {len(session_mgr.clients)}/{len(accounts)} reconnectés",
        parse_mode='Markdown'
    )

@auth_required
async def session_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les infos de session pour un compte donné"""
    if not context.args:
        # Lister toutes les sessions
        session_dir = "sessions"
        if os.path.exists(session_dir):
            files = os.listdir(session_dir)
            msg = f"**💾 Sessions backup:**\n{len(files)} fichiers\n\n"
            for f in files[:20]:
                size = os.path.getsize(f"{session_dir}/{f}")
                msg += f"📄 `{f}` ({size} bytes)\n"
            if len(files) > 20:
                msg += f"...+{len(files)-20}"
        else:
            msg = "📂 Aucune session backup"
        await update.message.reply_text(msg, parse_mode='Markdown')
        return
    
    phone = context.args[0]
    if not phone.startswith('+'):
        phone = '+' + phone
    
    session_string = db.get_account_session(phone)
    if session_string:
        await update.message.reply_text(
            f"✅ Session trouvée pour `{phone}`\n"
            f"Longueur: {len(session_string)} caractères",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"❌ Aucune session pour `{phone}`",
            parse_mode='Markdown'
        )

# ========== UTILITIES ==========

def _save_session_file(phone, session_string):
    """Sauvegarde la session dans un fichier de backup"""
    try:
        session_dir = "sessions"
        os.makedirs(session_dir, exist_ok=True)
        filename = phone.replace('+', '')
        filepath = f"{session_dir}/{filename}.session"
        with open(filepath, "w") as f:
            f.write(session_string)
        logger.info(f"💾 Session backup: {filepath}")
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde session {phone}: {e}")
        return False

def _remove_session_file(phone):
    """Supprime le fichier de session backup"""
    try:
        filename = phone.replace('+', '')
        filepath = f"sessions/{filename}.session"
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"🗑️ Session backup supprimée: {filepath}")
    except Exception as e:
        logger.error(f"Erreur suppression session {phone}: {e}")

def _restore_pending_from_db():
    """Restaure les pending login depuis la DB après redémarrage"""
    try:
        pending_list = db.get_all_pending()
        restored = 0
        for p in pending_list:
            phone = p['phone']
            try:
                client = create_telegram_client()
                # On ne connecte pas complètement, juste on prépare
                _pending[phone] = {
                    'client': None,  # Sera reconnecté à l'utilisation
                    'phone_code_hash': p.get('phone_code_hash', ''),
                    'user_id': p['user_id'],
                    'phone': phone,
                    'api_id': p.get('api_id', DEFAULT_API_ID),
                    'api_hash': p.get('api_hash', DEFAULT_API_HASH),
                }
                restored += 1
                logger.info(f"Restauré pending pour {phone}")
            except Exception as e:
                logger.error(f"Erreur restauration pending {phone}: {e}")
        logger.info(f"Restauré {restored} pending login depuis la DB")
        return restored
    except Exception as e:
        logger.error(f"Erreur restauration pending: {e}")
        return 0

# ========== INITIALISATION ==========

async def post_init(app: Application):
    logger.info("🚀 Démarrage du bot...")
    
    # Créer le dossier sessions s'il n'existe pas
    os.makedirs("sessions", exist_ok=True)
    
    # Restaurer les pending login depuis la DB
    _restore_pending_from_db()
    
    # Charger tous les comptes actifs
    await session_mgr.load_all_active_accounts()
    
    # Scraper les proxies si aucun en base
    if db.get_proxy_count() == 0:
        logger.info("🔌 Aucun proxy en base, scraping...")
        count = await proxy_scraper.scrape_and_store()
        logger.info(f"🔌 {count} proxies scrapés")
    
    logger.info(f"✅ Bot prêt: {len(session_mgr.clients)} comptes, {db.get_proxy_count()} proxies")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_account))
    app.add_handler(CommandHandler("co", verify_code))
    app.add_handler(CommandHandler("cod2", verify_2fa))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("702", report))
    app.add_handler(CommandHandler("scrape", scrape_proxies))
    app.add_handler(CommandHandler("del", remove_account))
    app.add_handler(CommandHandler("reconnect", reconnect))
    app.add_handler(CommandHandler("session", session_info))
    
    logger.info("🔄 Démarrage du polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
