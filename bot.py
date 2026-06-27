# bot.py
import asyncio
import logging
import os
import tempfile
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import BOT_TOKEN, AUTHORIZED_USERS, DEFAULT_API_ID, DEFAULT_API_HASH
from database import Database
from session_mgr import SessionManager
from reporter import Reporter
from proxy_scraper import ProxyScraper
from pyrogram import Client

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

db = Database()
session_mgr = SessionManager(db)
reporter = Reporter(db)
proxy_scraper = ProxyScraper(db)

authorized_users = set(AUTHORIZED_USERS)

# Dictionnaire pour stocker les clients en cours de connexion
_pending_clients = {}

def auth_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id not in authorized_users:
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@auth_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_active_accounts()
    proxies = db.get_proxy_count()
    
    msg = (
        f"🤖 **Bot prêt**\n\n"
        f"📱 Comptes: {len(session_mgr.clients)}/{len(accounts)} actifs\n"
        f"🔌 Proxies: {proxies} en base\n\n"
        f"**Commandes:**\n"
        f"`/add +33612345678` - Ajouter un compte\n"
        f"`/co 12345` - Code de vérification SMS\n"
        f"`/cod2 motdepasse` - Code 2FA\n"
        f"`/status` - Statut des comptes\n"
        f"`/702 @user` - Signaler\n"
        f"`/scrape` - Scraper des proxies\n"
        f"`/proxies` - Voir les proxies\n"
        f"`/del +336...` - Supprimer un compte\n"
        f"`/reconnect` - Reconnecter tous les comptes"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

@auth_required
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/add +33612345678"""
    
    if not context.args:
        await update.message.reply_text("Usage: `/add +33612345678`", parse_mode='Markdown')
        return
    
    phone = context.args[0]
    if not phone.startswith('+'):
        phone = '+' + phone
    
    # Vérifier si le compte existe déjà
    existing = db.get_account(phone)
    if existing and existing['status'] == 'active':
        await update.message.reply_text(f"ℹ️ `{phone}` est déjà actif", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(f"📱 Connexion de `{phone}`...", parse_mode='Markdown')
    
    try:
        # Récupérer un proxy
        proxy = db.get_proxy_cycle()
        proxy_dict = None
        if proxy:
            proxy_dict = {
                "scheme": proxy.get('protocol', 'socks5'),
                "hostname": proxy['address'],
                "port": proxy['port'],
                "username": proxy.get('username'),
                "password": proxy.get('password')
            }
        
        # Créer un client Pyrogram TEMPORAIRE (pas de fichier session)
        session_name = f"add_{phone.replace('+', '')}_{int(datetime.now().timestamp())}"
        
        client = Client(
            session_name,
            api_id=DEFAULT_API_ID,
            api_hash=DEFAULT_API_HASH,
            proxy=proxy_dict,
            workdir=tempfile.gettempdir(),
            in_memory=True
        )
        
        await client.connect()
        
        # Envoyer le code de vérification
        sent_code = await client.send_code(phone)
        
        # Stocker le client en attente
        _pending_clients[phone] = {
            'client': client,
            'phone_code_hash': sent_code.phone_code_hash,
            'phone': phone,
            'user_id': update.effective_user.id
        }
        
        # Ajouter à la base de données
        db.add_account(phone, DEFAULT_API_ID, DEFAULT_API_HASH)
        db.set_pending_login(update.effective_user.id, phone, DEFAULT_API_ID, DEFAULT_API_HASH, "code_sent")
        
        await msg.edit_text(
            f"✅ Code de vérification envoyé à `{phone}`\n\n"
            f"Utilise `/co CODE` pour valider\n"
            f"Exemple: `/co 12345`",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Erreur add_account {phone}: {e}")
        error_msg = str(e)
        
        if "PHONE_NUMBER_INVALID" in error_msg:
            await msg.edit_text(f"❌ Numéro invalide: `{phone}`\nFormat attendu: +33612345678", parse_mode='Markdown')
        elif "PHONE_NUMBER_FLOOD" in error_msg:
            await msg.edit_text("❌ Trop de tentatives. Attends quelques minutes.")
        elif "PHONE_NUMBER_BANNED" in error_msg:
            await msg.edit_text(f"❌ Le numéro `{phone}` est banni de Telegram", parse_mode='Markdown')
        else:
            await msg.edit_text(f"❌ Erreur: {error_msg[:200]}")

@auth_required
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/co 12345"""
    if not context.args:
        await update.message.reply_text("Usage: `/co 12345`", parse_mode='Markdown')
        return
    
    code = context.args[0]
    user_id = update.effective_user.id
    
    # Chercher le pending client pour cet utilisateur
    pending = None
    pending_phone = None
    for phone, data in list(_pending_clients.items()):
        if data.get('user_id') == user_id:
            pending = data
            pending_phone = phone
            break
    
    if not pending:
        # Vérifier aussi dans la base de données
        db_pending = db.get_pending_login(user_id)
        if db_pending:
            await update.message.reply_text(
                "❌ Session expirée. Le code a peut-être expiré.\n"
                "Refais `/add +336...` pour recommencer.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Aucune connexion en attente.\n"
                "Fais `/add +33612345678` d'abord.",
                parse_mode='Markdown'
            )
        return
    
    msg = await update.message.reply_text(f"🔄 Vérification du code pour `{pending_phone}`...", parse_mode='Markdown')
    
    try:
        client = pending['client']
        
        # Essayer de sign in
        try:
            await client.sign_in(
                phone_number=pending_phone,
                phone_code_hash=pending['phone_code_hash'],
                phone_code=code
            )
            
            # Succès !
            session_string = await client.export_session_string()
            
            # Sauvegarder dans la base de données
            db.update_account_session(pending_phone, session_string)
            db.update_account_status(pending_phone, 'active')
            db.remove_pending_login(user_id)
            
            # Ajouter aux clients actifs du session_mgr
            session_mgr.clients[pending_phone] = (client, pending.get('proxy'))
            
            # Nettoyer le pending
            del _pending_clients[pending_phone]
            
            await msg.edit_text(
                f"✅ **Compte connecté avec succès !**\n"
                f"📱 `{pending_phone}`\n\n"
                f"Tu peux maintenant signaler avec `/702 @cible`",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            error_str = str(e)
            
            # 2FA nécessaire
            if "Two-Step Verification" in error_str or "PASSWORD" in error_str or "2FA" in error_str:
                await msg.edit_text(
                    f"🔐 **Code 2FA requis**\n\n"
                    f"Ce compte a l'authentification à deux facteurs activée.\n"
                    f"Utilise `/cod2 TON_MOT_DE_PASSE`",
                    parse_mode='Markdown'
                )
                return
            
            # Code invalide
            if "PHONE_CODE_INVALID" in error_str:
                await msg.edit_text(
                    f"❌ Code invalide.\n"
                    f"Vérifie le code SMS et réessaie avec `/co CODE`",
                    parse_mode='Markdown'
                )
                return
            
            # Code expiré
            if "PHONE_CODE_EXPIRED" in error_str:
                await msg.edit_text(
                    f"❌ Code expiré.\n"
                    f"Refais `/add +336...` pour recevoir un nouveau code.",
                    parse_mode='Markdown'
                )
                del _pending_clients[pending_phone]
                return
            
            # Flood
            if "FLOOD" in error_str:
                await msg.edit_text("❌ Trop de tentatives. Attends 5 minutes.")
                return
            
            # Autre erreur
            await msg.edit_text(f"❌ Erreur: {error_str[:200]}")
            
    except Exception as e:
        logger.error(f"Erreur verify_code: {e}")
        await msg.edit_text(f"❌ Erreur: {str(e)[:200]}")

@auth_required
async def verify_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cod2 motdepasse"""
    if not context.args:
        await update.message.reply_text("Usage: `/cod2 mon_mot_de_passe`", parse_mode='Markdown')
        return
    
    password = ' '.join(context.args)
    user_id = update.effective_user.id
    
    # Chercher le pending client pour cet utilisateur
    pending = None
    pending_phone = None
    for phone, data in list(_pending_clients.items()):
        if data.get('user_id') == user_id:
            pending = data
            pending_phone = phone
            break
    
    if not pending:
        await update.message.reply_text(
            "❌ Aucune connexion en attente.\n"
            "Fais `/add +33612345678` d'abord.",
            parse_mode='Markdown'
        )
        return
    
    msg = await update.message.reply_text(f"🔄 Vérification 2FA pour `{pending_phone}`...", parse_mode='Markdown')
    
    try:
        client = pending['client']
        
        # Vérifier le mot de passe 2FA
        await client.check_password(password)
        
        # Succès !
        session_string = await client.export_session_string()
        
        # Sauvegarder
        db.update_account_session(pending_phone, session_string)
        db.update_account_status(pending_phone, 'active')
        db.remove_pending_login(user_id)
        
        # Ajouter aux clients actifs
        session_mgr.clients[pending_phone] = (client, pending.get('proxy'))
        
        # Nettoyer
        del _pending_clients[pending_phone]
        
        await msg.edit_text(
            f"✅ **Compte connecté avec 2FA !**\n"
            f"📱 `{pending_phone}`\n\n"
            f"Tu peux maintenant signaler avec `/702 @cible`",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        error_str = str(e)
        
        if "PASSWORD_HASH_INVALID" in error_str or "password" in error_str.lower():
            await msg.edit_text("❌ Mot de passe 2FA incorrect. Réessaie avec `/cod2 BON_MOT_DE_PASSE`", parse_mode='Markdown')
        elif "FLOOD" in error_str:
            await msg.edit_text("❌ Trop de tentatives. Attends 5 minutes.")
        else:
            await msg.edit_text(f"❌ Erreur: {error_str[:200]}")

@auth_required
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_all_accounts()
    active_accounts = db.get_active_accounts()
    proxies = db.get_active_proxies()
    
    msg = f"**📊 Status**\n\n"
    msg += f"**Comptes:** {len(accounts)} total\n"
    msg += f"**Connectés:** {len(session_mgr.clients)}/{len(active_accounts)} actifs\n"
    msg += f"**Proxies:** {len(proxies)} actifs\n\n"
    
    if session_mgr.clients:
        msg += "**Sessions actives:**\n"
        count = 0
        for phone in list(session_mgr.clients.keys()):
            if count >= 10:
                msg += f"...et {len(session_mgr.clients)-10} autres\n"
                break
            client, _ = session_mgr.clients[phone]
            try:
                me = await client.get_me()
                name = f"{me.first_name or ''} {me.last_name or ''}".strip() or "?"
                msg += f"✅ `{phone}` - {name}\n"
            except:
                msg += f"❌ `{phone}` - session expirée\n"
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
    
    if len(clients) < 2:
        await update.message.reply_text("⚠️ Minimum 2 comptes connectés. Ajoute des comptes avec `/add`", parse_mode='Markdown')
        return
    
    msg = await update.message.reply_text(
        f"🎯 Signalement de `{target}` avec {len(clients)} comptes...",
        parse_mode='Markdown'
    )
    
    try:
        success = await reporter.coordinated_report(clients, target)
        db.add_target(target)
        db.increment_target_reports(target)
        
        await msg.edit_text(
            f"✅ **Terminé**\n\n"
            f"🎯 Cible: `{target}`\n"
            f"📊 Réussis: {success}/{len(clients)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Erreur: `{str(e)[:200]}`", parse_mode='Markdown')

@auth_required
async def scrape_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🕷️ Scraping des proxies...")
    count = await proxy_scraper.scrape_and_store()
    await msg.edit_text(f"✅ {count} proxies ajoutés. Total: {db.get_proxy_count()}", parse_mode='Markdown')

@auth_required
async def list_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proxies = db.get_active_proxies()
    if not proxies:
        await update.message.reply_text("❌ Aucun proxy. Utilise `/scrape`", parse_mode='Markdown')
        return
    
    msg = f"**🔌 Proxies: {len(proxies)}**\n\n"
    for p in proxies[:20]:
        auth = f"{p['username']}:****@" if p.get('username') else ""
        msg += f"• `socks5://{auth}{p['address']}:{p['port']}`\n"
    
    if len(proxies) > 20:
        msg += f"\n...et {len(proxies)-20} autres"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

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
    msg = await update.message.reply_text("🔄 Reconnexion de tous les comptes...")
    await session_mgr.disconnect_all()
    await session_mgr.load_all_active_accounts()
    accounts = db.get_active_accounts()
    await msg.edit_text(f"✅ {len(session_mgr.clients)}/{len(accounts)} comptes reconnectés", parse_mode='Markdown')

async def post_init(app: Application):
    logger.info("🚀 Démarrage du bot...")
    
    # Charger les comptes actifs
    await session_mgr.load_all_active_accounts()
    
    # Scraper des proxies si besoin
    if db.get_proxy_count() == 0:
        logger.info("🕷️ Scraping automatique des proxies...")
        await proxy_scraper.scrape_and_store()
    
    accounts = db.get_active_accounts()
    logger.info(f"✅ Bot prêt: {len(session_mgr.clients)}/{len(accounts)} comptes connectés, {db.get_proxy_count()} proxies")

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_account))
    app.add_handler(CommandHandler("co", verify_code))
    app.add_handler(CommandHandler("cod2", verify_2fa))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("702", report))
    app.add_handler(CommandHandler("scrape", scrape_proxies))
    app.add_handler(CommandHandler("proxies", list_proxies))
    app.add_handler(CommandHandler("del", remove_account))
    app.add_handler(CommandHandler("reconnect", reconnect))
    
    logger.info("🚀 Bot prêt à fonctionner")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
