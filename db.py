import sqlite3
import logging
import os
from config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Account:
    def __init__(self, phone: str, session_string: str):
        self.phone = phone
        self.session_string = session_string


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

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
