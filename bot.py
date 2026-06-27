# bot.py
import asyncio
import logging
import os
import sys
import tempfile
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telethon import TelegramClient
from telethon.errors import *
from telethon.sessions import StringSession
from pyrogram import Client as PyroClient
from config import BOT_TOKEN, AUTHORIZED_USERS, DEFAULT_API_ID, DEFAULT_API_HASH
from database import Database
from session_mgr import SessionManager
from reporter import Reporter
from proxy_scraper import ProxyScraper

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

def auth_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in authorized_users:
            logger.warning(f"Utilisateur non authorisé: {update.effective_user.id}")
            await update.message.reply_text("⛔ Non authorisé")
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
    """
    Ajoute un compte via Telethon
    """
    if not context.args:
        await update.message.reply_text("Usage: `/add +22501234567`", parse_mode='Markdown')
        return
    
    phone = context.args[0]
    logger.info(f"📱 Tentative d'ajout: {phone}")
    
    # Nettoyage automatique du numéro
    phone = phone.strip()
    if not phone.startswith('+'):
        phone = '+' + phone
    
    # Supprimer le 0 après l'indicatif si présent (ex: +2250152401774 → +225152401774)
    # En fait, certains opérateurs acceptent les deux formats. On laisse tel quel.
    
    # Vérifier format
    if len(phone) < 10:
        await update.message.reply_text(f"❌ Numéro trop court: `{phone}`\nFormat: `+22501234567`", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(f"📱 Connexion de `{phone}`...\nPatientez...", parse_mode='Markdown')
    
    try:
        logger.debug(f"Création du client Telethon pour {phone}")
        
        # Créer client Telethon
        client = TelegramClient(
            StringSession(),
            DEFAULT_API_ID,
            DEFAULT_API_HASH,
            device_model="Telegram Purge Bot",
            system_version="Linux 4.19",
            app_version="1.0.0",
            connection_retries=3,
            timeout=30
        )
        
        logger.debug("Connexion au DC Telegram...")
        await client.connect()
        
        logger.debug(f"Vérification autorisation pour {phone}...")
        is_auth = await client.is_user_authorized()
        logger.debug(f"is_user_authorized: {is_auth}")
        
        if is_auth:
            # Déjà connecté
            session_string = client.session.save()
            db.update_account_session(phone, session_string)
            db.update_account_status(phone, 'active')
            
            # Ajouter à Pyrogram
            try:
                pyro = PyroClient(
                    f"pyro_{phone.replace('+', '')}",
                    api_id=DEFAULT_API_ID,
                    api_hash=DEFAULT_API_HASH,
                    session_string=session_string,
                    in_memory=True
                )
                await pyro.connect()
                session_mgr.clients[phone] = (pyro, None)
            except Exception as e:
                session_mgr.clients[phone] = (client, None)
            
            await msg.edit_text(f"ℹ️ `{phone}` déjà connecté !", parse_mode='Markdown')
            return
        
        logger.debug(f"Envoi du code à {phone}...")
        sent = await client.send_code_request(phone)
        logger.debug(f"Code envoyé! phone_code_hash: {sent.phone_code_hash}")
        
        # Stocker
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
            f"📨 Vérifie tes SMS sur ton téléphone\n"
            f"📝 Utilise `/co CODE` (ex: `/co 12345`)",
            parse_mode='Markdown'
        )
        logger.info(f"✅ Code envoyé avec succès à {phone}")
        
    except PhoneNumberInvalidError:
        logger.error(f"Numéro invalide: {phone}")
        await msg.edit_text(
            f"❌ **Numéro invalide**: `{phone}`\n\n"
            f"Format correct pour la Côte d'Ivoire:\n"
            f"`+22501234567` ou `+22505234567`\n\n"
            f"L'indicatif est `+225` suivi de 8 chiffres (sans le 0 après le 225)",
            parse_mode='Markdown'
        )
    except PhoneNumberBannedError:
        await msg.edit_text(f"❌ `{phone}` est banni de Telegram", parse_mode='Markdown')
    except PhoneNumberFloodError:
        await msg.edit_text(f"❌ Trop de tentatives pour `{phone}`. Attends 1 heure.", parse_mode='Markdown')
    except FloodWaitError as e:
        await msg.edit_text(f"❌ Flood attend: {e.seconds} secondes", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ Erreur add_account pour {phone}: {e}", exc_info=True)
        await msg.edit_text(
            f"❌ **Erreur**: `{str(e)[:300]}`\n\n"
            f"Vérifie que:\n"
            f"1. Le numéro est correct (+225...)\n"
            f"2. Tu as bien un compte Telegram sur ce numéro\n"
            f"3. Les API_ID et API_HASH dans config.py sont bons",
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
    
    logger.info(f"Vérification code pour user {user_id}: {code}")
    
    # Chercher le pending
    phone_to_verify = None
    pending_data = None
    for phone, data in list(_pending.items()):
        if data.get('user_id') == user_id:
            phone_to_verify = phone
            pending_data = data
            break
    
    if not pending_data:
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
            
            # Succès !
            logger.info(f"✅ {phone_to_verify} connecté avec succès!")
            session_string = client.session.save()
            
            db.update_account_session(phone_to_verify, session_string)
            db.update_account_status(phone_to_verify, 'active')
            db.remove_pending_login(user_id)
            
            # Ajouter à Pyrogram
            try:
                pyro = PyroClient(
                    f"pyro_{phone_to_verify.replace('+', '')}",
                    api_id=DEFAULT_API_ID,
                    api_hash=DEFAULT_API_HASH,
                    session_string=session_string,
                    in_memory=True
                )
                await pyro.connect()
                session_mgr.clients[phone_to_verify] = (pyro, None)
                logger.info(f"✅ Client Pyrogram créé pour {phone_to_verify}")
            except Exception as e:
                logger.warning(f"Pyrogram fail: {e}, fallback Telethon")
                session_mgr.clients[phone_to_verify] = (client, None)
            
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
    
    if not pending_data:
        await update.message.reply_text("❌ Aucune connexion en attente.", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(f"🔄 Vérification 2FA de `{phone_to_verify}`...", parse_mode='Markdown')
    
    try:
        client = pending_data['client']
        await client.sign_in(password=password)
        
        session_string = client.session.save()
        db.update_account_session(phone_to_verify, session_string)
        db.update_account_status(phone_to_verify, 'active')
        db.remove_pending_login(user_id)
        
        try:
            pyro = PyroClient(
                f"pyro_{phone_to_verify.replace('+', '')}",
                api_id=DEFAULT_API_ID,
                api_hash=DEFAULT_API_HASH,
                session_string=session_string,
                in_memory=True
            )
            await pyro.connect()
            session_mgr.clients[phone_to_verify] = (pyro, None)
        except:
            session_mgr.clients[phone_to_verify] = (client, None)
        
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
        await update.message.reply_text("Usage: `/del +225XXXXXXXX`", parse_mode='Markdown')
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
