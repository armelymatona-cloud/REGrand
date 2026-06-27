# bot.py
import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import BOT_TOKEN, AUTHORIZED_USERS
from database import Database
from session_mgr import SessionManager
from reporter import Reporter
from proxy_scraper import ProxyScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import os

# Remplacez vos anciennes lignes par celles-ci
API_ID = os.getenv("DEFAULT_API_ID")
API_HASH = os.getenv("DEFAULT_API_HASHH")

db = Database("bot.db")
session_mgr = SessionManager(db)
reporter = Reporter(db)
proxy_scraper = ProxyScraper(db)

authorized_users = set(AUTHORIZED_USERS)

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
    
    user_id = update.effective_user.id
    
    db.set_pending_login(user_id, phone, DEFAULT_API_ID, DEFAULT_API_HASH, "code_sent")
    db.add_account(phone, DEFAULT_API_ID, DEFAULT_API_HASH)
    
    success, msg, client = await session_mgr.start_login(phone, DEFAULT_API_ID, DEFAULT_API_HASH)
    
    if success:
        await update.message.reply_text(
            f"📱 Code envoyé à `{phone}`\n"
            f"Utilise `/co CODE` pour valider",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"❌ {msg}")

@auth_required
async def verify_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/co 12345"""
    if not context.args:
        await update.message.reply_text("Usage: /co 12345")
        return
    
    user_id = update.effective_user.id
    pending = db.get_pending_login(user_id)
    
    if not pending:
        await update.message.reply_text("❌ Aucune connexion en attente. Fais /add d'abord.")
        return
    
    phone = pending['phone']
    code = context.args[0]
    
    success, msg, session_string = await session_mgr.verify_code(phone, code)
    
    if success and session_string:
        db.update_account_session(phone, session_string)
        db.remove_pending_login(user_id)
        await update.message.reply_text(f"✅ **{phone} connecté!**", parse_mode='Markdown')
    else:
        await update.message.reply_text(msg)

@auth_required
async def verify_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cod2 motdepasse"""
    if not context.args:
        await update.message.reply_text("Usage: /cod2 mon_mot_de_passe")
        return
    
    user_id = update.effective_user.id
    pending = db.get_pending_login(user_id)
    
    if not pending:
        await update.message.reply_text("❌ Aucune connexion en attente")
        return
    
    phone = pending['phone']
    password = ' '.join(context.args)
    
    success, msg, session_string = await session_mgr.verify_2fa(phone, password)
    
    if success and session_string:
        db.update_account_session(phone, session_string)
        db.remove_pending_login(user_id)
        await update.message.reply_text(f"✅ **{phone} connecté avec 2FA!**", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ {msg}")

@auth_required
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_all_accounts()
    proxies = db.get_active_proxies()
    
    msg = f"**📊 Status**\n\n"
    msg += f"**Comptes:** {len(accounts)} total, {len(session_mgr.clients)} connectés\n"
    msg += f"**Proxies:** {len(proxies)} actifs\n\n"
    
    if session_mgr.clients:
        msg += "**Sessions actives:**\n"
        for phone in list(session_mgr.clients.keys())[:10]:
            client, _ = session_mgr.clients[phone]
            try:
                me = await client.get_me()
                name = f"{me.first_name}" if me else "?"
                msg += f"✅ `{phone}` - {name}\n"
            except:
                msg += f"❌ `{phone}` - session expirée\n"
    
    if len(session_mgr.clients) > 10:
        msg += f"...et {len(session_mgr.clients)-10} autres\n"
    
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
        await update.message.reply_text("⚠️ Minimum 2 comptes connectés")
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
            f"📊 Succès: {success}/{len(clients)}",
            parse_mode='Markdown'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Erreur: `{e}`", parse_mode='Markdown')

@auth_required
async def scrape_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🕷️ Scraping des proxies...")
    count = await proxy_scraper.scrape_and_store()
    await msg.edit_text(f"✅ {count} proxies ajoutés. Total: {db.get_proxy_count()}", parse_mode='Markdown')

@auth_required
async def list_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proxies = db.get_active_proxies()
    if not proxies:
        await update.message.reply_text("❌ Aucun proxy. Utilise /scrape")
        return
    
    msg = f"**🔌 Proxies: {len(proxies)}**\n\n"
    for p in proxies[:20]:
        auth = f"{p['username']}:****@" if p['username'] else ""
        msg += f"• `socks5://{auth}{p['address']}:{p['port']}`\n"
    
    if len(proxies) > 20:
        msg += f"\n...et {len(proxies)-20} autres"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

@auth_required
async def remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /del +336XXXXXXXX")
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
    await msg.edit_text(f"✅ {len(session_mgr.clients)}/{len(accounts)} comptes connectés", parse_mode='Markdown')

async def post_init(app: Application):
    logger.info("🚀 Démarrage...")
    await session_mgr.load_all_active_accounts()
    if db.get_proxy_count() == 0:
        logger.info("🕷️ Scraping automatique des proxies...")
        await proxy_scraper.scrape_and_store()
    accounts = db.get_active_accounts()
    logger.info(f"✅ Prêt: {len(session_mgr.clients)}/{len(accounts)} comptes, {db.get_proxy_count()} proxies")

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
    
    logger.info("🚀 Bot prêt")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
