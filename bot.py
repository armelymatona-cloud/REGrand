# bot.py
import asyncio
import logging
import os
import tempfile
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pyrogram import Client
from telethon import TelegramClient
from telethon.errors import *
from telethon.sessions import StringSession
from config import BOT_TOKEN, AUTHORIZED_USERS, DEFAULT_API_ID, DEFAULT_API_HASH
from database import Database
from session_mgr import SessionManager
from reporter import Reporter
from proxy_scraper import ProxyScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

db = Database()
session_mgr = SessionManager(db)
reporter = Reporter(db)
proxy_scraper = ProxyScraper(db)

authorized_users = set(AUTHORIZED_USERS)

# Stockage des connexions en cours
_pending = {}

def auth_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in authorized_users:
            await update.message.reply_text("⛔ Non autorisé")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@auth_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_active_accounts()
    proxies = db.get_proxy_count()
    
    msg = (
        f"🤖 **TELEGRAM PURGE BOT**\n\n"
        f"📱 Comptes: {len(session_mgr.clients)}/{len(accounts)} actifs\n"
        f"🔌 Proxies: {proxies} en base\n\n"
        f"**Commandes:**\n"
        f"`/add +33612345678` - Ajouter un compte\n"
        f"`/co 12345` - Code de vérification\n"
        f"`/cod2 mdp` - Code 2FA\n"
        f"`/status` - Statut\n"
        f"`/702 @user` - Signaler\n"
        f"`/scrape` - Scraper proxies\n"
        f"`/del +336...` - Supprimer\n"
        f"`/reconnect` - Reconnecter"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

@auth_required
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Ajoute un compte en utilisant Telethon (compatible Railway)
    """
    if not context.args:
        await update.message.reply_text("Usage: `/add +33612345678`", parse_mode='Markdown')
        return
    
    phone = context.args[0]
    if not phone.startswith('+'):
        phone = '+' + phone
    
    # Vérifier si déjà actif
    existing = db.get_account(phone)
    if existing and existing['status'] == 'active':
        await update.message.reply_text(f"ℹ️ `{phone}` déjà actif", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(f"📱 Connexion de `{phone}`...", parse_mode='Markdown')
    
    try:
        # Créer un client Telethon (plus fiable que Pyrogram sur Railway)
        session_name = f"railway_{phone.replace('+', '')}_{int(datetime.now().timestamp())}"
        
        client = TelegramClient(
            StringSession(),  # Session en mémoire, PAS de fichier
            DEFAULT_API_ID,
            DEFAULT_API_HASH,
            device_model="Server",
            system_version="Linux 4.19",
            app_version="Telegram Purge Bot 1.0"
        )
        
        await client.connect()
        
        # Vérifier si déjà autorisé
        if await client.is_user_authorized():
            await msg.edit_text(f"ℹ️ `{phone}` déjà connecté sur Telethon", parse_mode='Markdown')
            session_string = client.session.save()
            db.update_account_session(phone, session_string)
            db.update_account_status(phone, 'active')
            
            # Ajouter aux clients actifs
            try:
                pyro_client = Client(
                    f"pyro_{phone.replace('+', '')}",
                    api_id=DEFAULT_API_ID,
                    api_hash=DEFAULT_API_HASH,
                    session_string=session_string,
                    in_memory=True,
                    workdir=tempfile.gettempdir()
                )
                await pyro_client.connect()
                session_mgr.clients[phone] = (pyro_client, None)
            except Exception as e:
                logger.warning(f"Impossible de créer client Pyro: {e}")
                session_mgr.clients[phone] = (client, None)
            
            return
        
        # Envoyer le code
        sent = await client.send_code_request(phone)
        
        # Stocker pour validation
        _pending[phone] = {
            'client': client,
            'phone_code_hash': sent.phone_code_hash,
            'user_id': update.effective_user.id,
            'phone': phone
        }
        
        db.add_account(phone, DEFAULT_API_ID, DEFAULT_API_HASH)
        db.set_pending_login(update.effective_user.id, phone, DEFAULT_API_ID, DEFAULT_API_HASH, "code_sent")
        
        await msg.edit_text(
            f"✅ **Code envoyé à** `{phone}`\n\n"
            f"Utilise `/co CODE`\n"
            f"Ex: `/co 12345`",
            parse_mode='Markdown'
        )
        
    except PhoneNumberInvalidError:
        await msg.edit_text(f"❌ Numéro invalide: `{phone}`", parse_mode='Markdown')
    except PhoneNumberBannedError:
        await msg.edit_text(f"❌ `{phone}` est banni de Telegram", parse_mode='Markdown')
   例外 FloodWaitError as e:
        await msg.edit_text(f"❌ Flood wait: {e.seconds} secondes. Attends.")
    except Exception as e:
        logger.error(f"Erreur add: {e}")
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}")

@auth_required
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/co 12345"""
    if not context.args:
        await update.message.reply_text("Usage: `/co 12345`", parse_mode='Markdown')
        return
    
    code = context.args[0]
    user_id = update.effective_user.id
    
    # Chercher la session en attente pour cet utilisateur
    phone_to_verify = None
    pending_data = None
    for phone, data in list(_pending.items()):
        if data.get('user_id') == user_id:
            phone_to_verify = phone
            pending_data = data
            break
    
    if not pending_data:
        await update.message.reply_text("❌ Aucune connexion en attente. Fais `/add +336...` d'abord.", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(f"🔄 Vérification de `{phone_to_verify}`...", parse_mode='Markdown')
    
    try:
        client = pending_data['client']
        
        # Essayer de sign in
        try:
            await client.sign_in(
                phone=phone_to_verify,
                code=code,
                phone_code_hash=pending_data['phone_code_hash']
            )
            
            # Succès !
            session_string = client.session.save()
            
            # Sauvegarder en base
            db.update_account_session(phone_to_verify, session_string)
            db.update_account_status(phone_to_verify, 'active')
            db.remove_pending_login(user_id)
            
            # Créer un client Pyrogram pour le reporting
            try:
                pyro_client = Client(
                    f"pyro_{phone_to_verify.replace('+', '')}",
                    api_id=DEFAULT_API_ID,
                    api_hash=DEFAULT_API_HASH,
                    session_string=session_string,
                    in_memory=True,
                    workdir=tempfile.gettempdir()
                )
                await pyro_client.connect()
                session_mgr.clients[phone_to_verify] = (pyro_client, None)
            except Exception as e:
                # Fallback: utiliser Telethon
                logger.warning(f"Pyrogram fail, fallback Telethon: {e}")
                session_mgr.clients[phone_to_verify] = (client, None)
            
            # Nettoyer
            del _pending[phone_to_verify]
            
            await msg.edit_text(
                f"✅ **Compte connecté !**\n"
                f"📱 `{phone_to_verify}`\n\n"
                f"Utilise `/702 @cible` pour signaler",
                parse_mode='Markdown'
            )
            
        except PhoneCodeInvalidError:
            await msg.edit_text("❌ Code invalide. Vérifie le SMS et réessaie.", parse_mode='Markdown')
        except PhoneCodeExpiredError:
            await msg.edit_text("❌ Code expiré. Refais `/add +336...`", parse_mode='Markdown')
        except SessionPasswordNeededError:
            # 2FA requis
            await msg.edit_text(
                f"🔐 **Code 2FA requis**\n\n"
                f"Ce compte a l'authentification à deux facteurs.\n"
                f"Utilise `/cod2 TON_MOT_DE_PASSE`",
                parse_mode='Markdown'
            )
        except FloodWaitError as e:
            await msg.edit_text(f"❌ Flood wait: {e.seconds}s")
        except Exception as e:
            await msg.edit_text(f"❌ Erreur: {str(e)[:200]}")
            
    except Exception as e:
        logger.error(f"Erreur verify: {e}")
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
    
    if not pending_data:
        await update.message.reply_text("❌ Aucune connexion en attente.", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(f"🔄 Vérification 2FA de `{phone_to_verify}`...", parse_mode='Markdown')
    
    try:
        client = pending_data['client']
        
        await client.sign_in(password=password)
        
        # Succès
        session_string = client.session.save()
        
        db.update_account_session(phone_to_verify, session_string)
        db.update_account_status(phone_to_verify, 'active')
        db.remove_pending_login(user_id)
        
        # Ajouter à session_mgr
        try:
            pyro_client = Client(
                f"pyro_{phone_to_verify.replace('+', '')}",
                api_id=DEFAULT_API_ID,
                api_hash=DEFAULT_API_HASH,
                session_string=session_string,
                in_memory=True,
                workdir=tempfile.gettempdir()
            )
            await pyro_client.connect()
            session_mgr.clients[phone_to_verify] = (pyro_client, None)
        except:
            session_mgr.clients[phone_to_verify] = (client, None)
        
        del _pending[phone_to_verify]
        
        await msg.edit_text(
            f"✅ **Compte connecté (2FA) !**\n"
            f"📱 `{phone_to_verify}`",
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
    msg += f"🔌 Proxies: {db.get_proxy_count()}\n\n"
    
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
    msg = await update.message.reply_text("🕷️ Scraping...")
    count = await proxy_scraper.scrape_and_store()
    await msg.edit_text(f"✅ {count} proxies ajoutés. Total: {db.get_proxy_count()}", parse_mode='Markdown')

@auth_required
async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/del +336XXXXXXXX`", parse_mode='Markdown')
        return
    phone = context.args[0]
    if not phone.startswith('+'):
        phone = '+' + phone
    await session_mgr.disconnect_account(phone)
    db.remove_account(phone)
    await update.message.reply_text(f"🗑️ `{phone}` supprimé", parse_mode='Markdown')

@auth_required
async def reconnect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 Reconnexion...")
    await session_mgr.disconnect_all()
    await session_mgr.load_all_active_accounts()
    accounts = db.get_active_accounts()
    await msg.edit_text(f"✅ {len(session_mgr.clients)}/{len(accounts)} reconnectés", parse_mode='Markdown')

async def post_init(app: Application):
    logger.info("🚀 Démarrage...")
    await session_mgr.load_all_active_accounts()
    if db.get_proxy_count() == 0:
        await proxy_scraper.scrape_and_store()
    logger.info(f"✅ Prêt: {len(session_mgr.clients)} comptes, {db.get_proxy_count()} proxies")

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
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
