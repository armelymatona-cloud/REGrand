import logging
import aiohttp
import asyncio
import re

logger = logging.getLogger(__name__)


class ProxyScraper:
    SOURCES = [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http",
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4",
        "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    ]

    def __init__(self, db):
        self.db = db
        self.session = None

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15),
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )

    def _parse_proxies(self, text):
        pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b'
        return list(set(re.findall(pattern, text)))

    async def _scrape_source(self, url):
        proxies = []
        try:
            await self._ensure_session()
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    proxies = self._parse_proxies(text)
                    if proxies:
                        logger.info(f"✅ Scrapé: {url} ({len(proxies)} proxies)")
        except Exception:
            pass
        return proxies

    async def scrape_and_store(self):
        logger.info("🚀 Scraping des proxies...")
        all_proxies = []
        tasks = [self._scrape_source(url) for url in self.SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_proxies.extend(result)

        all_proxies = list(set(all_proxies))

        if self.session and not self.session.closed:
            await self.session.close()

        if all_proxies:
            new_count = self.db.add_proxies(all_proxies)
            logger.info(f"🎉 {new_count} nouveaux proxies (total: {self.db.get_proxy_count()})")
            return new_count
        return 0
