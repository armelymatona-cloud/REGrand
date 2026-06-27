import asyncio
import aiohttp
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class ProxyScraper:
    def __init__(self, db):
        self.db = db
        # Limite à 3 connexions simultanées pour ne pas saturer la RAM
        self.connector = aiohttp.TCPConnector(limit=3)
        self.timeout = aiohttp.ClientTimeout(total=20)

    async def fetch_url(self, session, url):
        try:
            async with session.get(url, timeout=self.timeout) as resp:
                if resp.status == 200:
                    return await resp.text()
        except Exception as e:
            logger.debug(f"Erreur sur {url}: {e}")
        return None

    async def scrape_and_store(self):
        logger.info("🚀 Démarrage du scraping sécurisé...")
        
        # Liste des sources (ajoutez toutes les vôtres ici)
        urls = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5",
            # Ajoutez vos autres liens ici...
        ]

        all_proxies = []
        async with aiohttp.ClientSession(connector=self.connector) as session:
            for url in urls:
                text = await self.fetch_url(session, url)
                if text:
                    # Traitement simple par ligne pour économiser la RAM
                    lines = text.splitlines()
                    for line in lines:
                        parts = line.split(':')
                        if len(parts) == 2:
                            all_proxies.append({'ip': parts[0], 'port': int(parts[1]), 'protocol': 'socks5'})
                
                # LA "RESPIRATION" : crucial pour Railway
                await asyncio.sleep(2) 
                logger.info(f"✅ Scrapé : {url}")

        # Déduplication légère
        unique_proxies = {f"{p['ip']}:{p['port']}": p for p in all_proxies}.values()
        
        # Stockage
        stored = self.db.add_proxies_batch(list(unique_proxies))
        logger.info(f"🎉 Scraping terminé. {stored} proxies stockés.")
        return stored
