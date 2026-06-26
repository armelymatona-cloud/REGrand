# proxy_scraper.py
import aiohttp
import asyncio
import re
import logging
from typing import List, Dict
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProxyScraper:
    def __init__(self, db: Database):
        self.db = db
        self.sources = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy_list.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
            "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
        ]
    
    async def fetch_proxies_from_url(self, session: aiohttp.ClientSession, url: str) -> List[str]:
        """Récupère les proxies depuis une URL"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    text = await response.text()
                    proxies = []
                    for line in text.splitlines():
                        line = line.strip()
                        if line and ':' in line and not line.startswith('#'):
                            # Format: ip:port ou ip:port:user:pass
                            parts = line.split(':')
                            if len(parts) >= 2:
                                proxies.append(line)
                    logger.info(f"📡 {url}: {len(proxies)} proxies")
                    return proxies
                return []
        except Exception as e:
            logger.warning(f"⚠️ {url}: {e}")
            return []
    
    async def scrape_all(self) -> List[Dict]:
        """Scrape les proxies de toutes les sources"""
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch_proxies_from_url(session, url) for url in self.sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_proxies = []
        seen = set()
        
        for proxy_list in results:
            if isinstance(proxy_list, list):
                for proxy_str in proxy_list:
                    if proxy_str not in seen:
                        seen.add(proxy_str)
                        parsed = self.parse_proxy_string(proxy_str)
                        if parsed:
                            all_proxies.append(parsed)
        
        return all_proxies
    
    def parse_proxy_string(self, proxy_str: str) -> Dict:
        """Parse une chaîne proxy en dict structuré"""
        parts = proxy_str.strip().split(':')
        
        if len(parts) == 2:
            # ip:port
            return {
                'address': parts[0],
                'port': int(parts[1]),
                'username': None,
                'password': None,
                'protocol': 'socks5'
            }
        elif len(parts) == 4:
            # ip:port:user:pass
            return {
                'address': parts[0],
                'port': int(parts[1]),
                'username': parts[2],
                'password': parts[3],
                'protocol': 'socks5'
            }
        return None
    
    async def check_proxy(self, proxy: Dict) -> bool:
        """Teste si un proxy est fonctionnel (connexion basique)"""
        try:
            proxy_url = f"socks5://{proxy['address']}:{proxy['port']}"
            if proxy['username']:
                proxy_url = f"socks5://{proxy['username']}:{proxy['password']}@{proxy['address']}:{proxy['port']}"
            
            import aiohttp_socks
            connector = aiohttp_socks.ProxyConnector.from_url(proxy_url)
            
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get("https://api.telegram.org/", timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    return resp.status == 200
        except:
            return False
    
    async def scrape_and_store(self) -> int:
        """Scrape, check et stocke les proxies valides"""
        logger.info("🕷️ Scraping des proxies...")
        raw_proxies = await self.scrape_all()
        logger.info(f"📦 {len(raw_proxies)} proxies trouvés, vérification en cours...")
        
        valid_count = 0
        # On vérifie un échantillon (trop long de tous les tester)
        sample_size = min(50, len(raw_proxies))
        import random
        sample = random.sample(raw_proxies, sample_size)
        
        for proxy in sample:
            if await self.check_proxy(proxy):
                if self.db.add_proxy(**proxy):
                    valid_count += 1
        
        # Ajoute le reste (non vérifié) si on veut plus de volume
        # self.db.add_proxies_bulk(raw_proxies[sample_size:])
        
        logger.info(f"✅ {valid_count} proxies valides stockés")
        return valid_count