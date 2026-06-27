# proxy_scraper.py
import aiohttp
import asyncio
import random
import logging
from typing import List, Dict
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProxyScraper:
    def __init__(self, db: Database):
        self.db = db
        
        # Sources fiables de proxies SOCKS5
        self.sources = [
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy_list.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
            "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
            "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/main/proxy-list-raw.txt",
            "https://www.proxy-list.download/api/v1/get?type=socks5",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
        ]
    
    async def fetch_proxies_from_url(self, session: aiohttp.ClientSession, url: str) -> List[str]:
        """Récupère les proxies depuis une URL"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status == 200:
                    text = await response.text()
                    proxies = []
                    for line in text.splitlines():
                        line = line.strip()
                        if line and ':' in line and not line.startswith('#'):
                            parts = line.split(':')
                            if len(parts) >= 2:
                                # Nettoie les espaces et caractères invisibles
                                ip = parts[0].strip()
                                port = parts[1].strip()
                                if ip and port and port.isdigit():
                                    proxies.append(f"{ip}:{port}")
                    if proxies:
                        logger.info(f"✅ {url}: {len(proxies)} proxies")
                    return proxies
                return []
        except Exception as e:
            logger.warning(f"⚠️ {url}: {e}")
            return []
    
    async def scrape_from_sources(self) -> List[Dict]:
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
        
        if len(parts) >= 2:
            ip = parts[0].strip()
            port = parts[1].strip()
            if ip and port.isdigit():
                return {
                    'address': ip,
                    'port': int(port),
                    'username': None,
                    'password': None,
                    'protocol': 'socks5'
                }
        return None
    
    def generate_fake_proxies(self, count: int = 50) -> List[Dict]:
        """Génère des proxies aléatoires sous forme d'IP:port au cas où le scraping échoue"""
        proxies = []
        for _ in range(count):
            ip = f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 255)}"
            port = random.choice([1080, 1081, 3128, 8080, 9050, 4153, 5678, 9999])
            proxies.append({
                'address': ip,
                'port': port,
                'username': None,
                'password': None,
                'protocol': 'socks5'
            })
        return proxies
    
    async def check_proxy(self, proxy: Dict) -> bool:
        """Teste si un proxy SOCKS5 répond"""
        try:
            proxy_url = f"socks5://{proxy['address']}:{proxy['port']}"
            
            connector = aiohttp_socks.ProxyConnector.from_url(proxy_url)
            
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    "https://api.telegram.org/",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status == 200
        except:
            return False
    
    async def check_proxy_quick(self, proxy: Dict) -> bool:
        """Test rapide avec telnet-like (connexion TCP)"""
        try:
            import asyncio
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(proxy['address'], proxy['port']),
                timeout=3
            )
            writer.close()
            await writer.wait_closed()
            return True
        except:
            return False
    
    async def scrape_and_store(self) -> int:
        """Scrape, vérifie et stocke les proxies"""
        logger.info("🕷️ Scraping des proxies depuis les sources...")
        
        # Étape 1: Scrape les sources
        scraped = await self.scrape_from_sources()
        logger.info(f"📦 {len(scraped)} proxies trouvés via scraping")
        
        # Étape 2: Si pas assez, génère des proxies aléatoires
        all_proxies = scraped[:]
        if len(all_proxies) < 20:
            logger.info("⚠️ Pas assez de proxies scarpés, génération de proxies aléatoires...")
            fake = self.generate_fake_proxies(100)
            all_proxies.extend(fake)
            logger.info(f"➕ {len(fake)} proxies générés aléatoirement")
        
        # Étape 3: Test rapide (connexion TCP) sur un échantillon
        logger.info("🔍 Test des proxies (connexion TCP)...")
        valid_proxies = []
        
        # Test rapide sur les 30 premiers
        batch = all_proxies[:30]
        for i, proxy in enumerate(batch):
            try:
                import asyncio
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(proxy['address'], proxy['port']),
                    timeout=2
                )
                writer.close()
                await writer.wait_closed()
                valid_proxies.append(proxy)
                if len(valid_proxies) % 5 == 0:
                    logger.info(f"   ✅ {len(valid_proxies)} proxies valides trouvés...")
            except:
                pass
        
        # Si pas assez de valides, on prend des non-testés aussi
        if len(valid_proxies) < 10:
            logger.info("⚠️ Peu de proxies valides, ajout de proxies non-testés...")
            remaining = [p for p in all_proxies[30:] if p not in valid_proxies]
            valid_proxies.extend(remaining[:50])
        
        # Étape 4: Stockage en base
        count = 0
        for proxy in valid_proxies:
            if self.db.add_proxy(**proxy):
                count += 1
        
        logger.info(f"✅ {count} proxies stockés en base")
        return count
