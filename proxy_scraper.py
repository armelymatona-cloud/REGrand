import logging
from database import Database

logger = logging.getLogger(__name__)

class ProxyScraper:
    def __init__(self, db: Database):
        self.db = db

    async def scrape_and_store(self) -> int:
        # Exemple : scraper depuis des sources publiques
        proxies = [
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
        try:
            import aiohttp
            from bs4 import BeautifulSoup
            async with aiohttp.ClientSession() as session:
                async with session.get("https://free-proxy-list.net/") as resp:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "lxml")
                    for row in soup.select("table.table tbody tr"):
                        cells = row.find_all("td")
                        if len(cells) >= 2:
                            ip = cells[0].text.strip()
                            port = cells[1].text.strip()
                            proxies.append(f"{ip}:{port}")
        except Exception as e:
            logger.error(f"Erreur scraping proxies: {e}")

        if proxies:
            return self.db.add_proxies(proxies)
        return 0
