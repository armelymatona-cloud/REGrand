import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ProxyScraper:
    def __init__(self, db):
        self.db = db

    async def scrape_and_store(self) -> int:
        proxies = []
        sources = [
            "https://free-proxy-list.net/",
            "https://www.sslproxies.org/",
        ]
        for url in sources:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=15) as resp:
                        html = await resp.text()
                        soup = BeautifulSoup(html, "lxml")
                        for row in soup.select("table.table tbody tr"):
                            cells = row.find_all("td")
                            if len(cells) >= 2:
                                ip = cells[0].text.strip()
                                port = cells[1].text.strip()
                                proxies.append(f"{ip}:{port}")
            except Exception as e:
                logger.error(f"Erreur scraping {url}: {e}")

        if proxies:
            added = self.db.add_proxies(proxies)
            logger.info(f"{added} nouveaux proxies ajoutés")
            return added
        return 0
