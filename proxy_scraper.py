import asyncio
import aiohttp
import re
import logging
import random
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

class ProxyScraper:
    def __init__(self, db):
        self.db = db
        self.timeout = aiohttp.ClientTimeout(total=15)
        
        # User-Agents réalistes
        self.user_agents = [
            "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.165 Mobile Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 13; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.159 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 14; Xiaomi 23127PN0CG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Mobile Safari/537.36",
        ]
    
    def _get_headers(self):
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    
    def _parse_proxy_string(self, line):
        """Parse une ligne de proxy au format ip:port ou protocol://ip:port"""
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//'):
            return None
        
        protocol = "socks5"
        username = None
        password = None
        
        # Format: protocol://user:pass@ip:port
        match = re.match(r'(https?|socks4|socks5)://(?:(.+?):(.+?)@)?([\d.]+):(\d+)', line)
        if match:
            proto = match.group(1)
            if proto == 'socks4':
                protocol = 'socks4'
            elif proto == 'socks5':
                protocol = 'socks5'
            elif proto == 'http' or proto == 'https':
                protocol = 'http'
            username = match.group(2)
            password = match.group(3)
            ip = match.group(4)
            port = int(match.group(5))
            return {'ip': ip, 'port': port, 'protocol': protocol, 'username': username, 'password': password}
        
        # Format: ip:port
        match = re.match(r'([\d.]+):(\d+)', line)
        if match:
            return {'ip': match.group(1), 'port': int(match.group(2)), 'protocol': protocol}
        
        return None
    
    async def _fetch_url(self, url, source_name="unknown"):
        """Télécharge le contenu d'une URL avec gestion d'erreur"""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=self._get_headers()) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        logger.debug(f"✅ {source_name}: {len(text)} bytes reçus")
                        return text
                    else:
                        logger.warning(f"⚠️ {source_name}: HTTP {resp.status}")
                        return None
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ {source_name}: Timeout")
            return None
        except Exception as e:
            logger.error(f"❌ {source_name}: {e}")
            return None
    
    async def _scrape_geonode(self):
        """Scrape proxies depuis GeoNode"""
        proxies = []
        for page in range(1, 4):
            url = f"https://proxylist.geonode.com/api/proxy-list?limit=100&page={page}&sort_by=lastChecked&sort_type=desc"
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.get(url, headers=self._get_headers()) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for p in data.get('data', []):
                                proxy = {
                                    'ip': p.get('ip'),
                                    'port': int(p.get('port', 0)),
                                    'protocol': p.get('protocols', ['socks5'])[0] if p.get('protocols') else 'socks5',
                                    'country': p.get('country'),
                                    'anonymity': p.get('anonymityLevel'),
                                    'response_time_ms': p.get('latency'),
                                }
                                if proxy['ip'] and proxy['port']:
                                    proxies.append(proxy)
            except Exception as e:
                logger.error(f"GeoNode page {page}: {e}")
                continue
        logger.info(f"GeoNode: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_socks5_proxy(self):
        """Scrape depuis socks5-proxy.net"""
        proxies = []
        url = "https://www.socks5-proxy.net/"
        text = await self._fetch_url(url, "socks5-proxy.net")
        if text:
            soup = BeautifulSoup(text, 'html.parser')
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        ip = cols[0].get_text(strip=True)
                        port_text = cols[1].get_text(strip=True)
                        try:
                            port = int(port_text)
                            proxies.append({
                                'ip': ip,
                                'port': port,
                                'protocol': 'socks5',
                                'country': cols[3].get_text(strip=True) if len(cols) > 3 else None,
                            })
                        except ValueError:
                            continue
        logger.info(f"socks5-proxy.net: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_spys_one(self):
        """Scrape depuis spys.one"""
        proxies = []
        url = "https://spys.one/en/socks-proxy-list/"
        text = await self._fetch_url(url, "spys.one")
        if text:
            # Spys.one utilise des patterns spécifiques
            pattern = re.compile(r'(\d+\.\d+\.\d+\.\d+):(\d+)[^<]*<[^>]*>(\w+)')
            for match in pattern.finditer(text):
                proxies.append({
                    'ip': match.group(1),
                    'port': int(match.group(2)),
                    'protocol': 'socks5',
                    'country': match.group(3),
                })
        logger.info(f"spys.one: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_proxyscrape(self):
        """Scrape depuis proxyscrape.com (API)"""
        proxies = []
        urls = [
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&timeout=10000&country=all",
        ]
        
        for url in urls:
            protocol = 'socks5' if 'socks5' in url else ('socks4' if 'socks4' in url else 'http')
            text = await self._fetch_url(url, f"proxyscrape-{protocol}")
            if text:
                for line in text.split('\n'):
                    parsed = self._parse_proxy_string(line)
                    if parsed:
                        parsed['protocol'] = protocol
                        proxies.append(parsed)
        logger.info(f"proxyscrape: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_openproxy(self):
        """Scrape depuis openproxy.space"""
        proxies = []
        url = "https://openproxy.space/list/socks5"
        text = await self._fetch_url(url, "openproxy.space")
        if text:
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            ip = item.get('ip')
                            port = item.get('port')
                            if ip and port:
                                proxies.append({
                                    'ip': ip,
                                    'port': int(port),
                                    'protocol': 'socks5',
                                })
            except json.JSONDecodeError:
                # Fallback: format texte simple
                for line in text.split('\n'):
                    parsed = self._parse_proxy_string(line)
                    if parsed:
                        proxies.append(parsed)
        logger.info(f"openproxy.space: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_free_proxy_list(self):
        """Scrape depuis free-proxy-list.net"""
        proxies = []
        url = "https://free-proxy-list.net/"
        text = await self._fetch_url(url, "free-proxy-list.net")
        if text:
            soup = BeautifulSoup(text, 'html.parser')
            table = soup.find('table', class_='table')
            if table:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        ip = cols[0].get_text(strip=True)
                        port = cols[1].get_text(strip=True)
                        try:
                            proxies.append({
                                'ip': ip,
                                'port': int(port),
                                'protocol': 'http',
                                'country': cols[3].get_text(strip=True) if len(cols) > 3 else None,
                                'anonymity': cols[4].get_text(strip=True) if len(cols) > 4 else None,
                            })
                        except ValueError:
                            continue
        logger.info(f"free-proxy-list.net: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_sockslist(self):
        """Scrape depuis sockslist.net"""
        proxies = []
        url = "https://sockslist.net/list/socks5/1"
        text = await self._fetch_url(url, "sockslist.net")
        if text:
            soup = BeautifulSoup(text, 'html.parser')
            # Chercher les adresses IP dans le contenu
            pattern = re.compile(r'(\d+\.\d+\.\d+\.\d+)[:\s]+(\d+)')
            for match in pattern.finditer(text):
                proxies.append({
                    'ip': match.group(1),
                    'port': int(match.group(2)),
                    'protocol': 'socks5',
                })
        logger.info(f"sockslist.net: {len(proxies)} proxies")
        return proxies
    
    async def _validate_proxy(self, proxy):
        """Valide un proxy en testant la connexion TCP et SOCKS5"""
        try:
            ip = proxy['ip']
            port = proxy['port']
            protocol = proxy.get('protocol', 'socks5')
            
            # Test TCP de base
            start = asyncio.get_event_loop().time()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=8
            )
            elapsed = int((asyncio.get_event_loop().time() - start) * 1000)
            
            # Test SOCKS5 handshake si c'est un proxy SOCKS
            if protocol in ('socks5', 'socks4'):
                # Envoi du handshake SOCKS5
                if protocol == 'socks5':
                    writer.write(b'\x05\x01\x00')  # SOCKS5, 1 auth method, no auth
                else:
                    writer.write(b'\x04\x01\x00\x50\x00\x00\x00\x00\x00\x00\x00\x00')  # SOCKS4
                await writer.drain()
                response = await asyncio.wait_for(reader.read(2), timeout=5)
                
                if protocol == 'socks5' and len(response) == 2 and response[0] == 5:
                    # Handshake SOCKS5 réussi
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except:
                        pass
                    proxy['response_time_ms'] = elapsed
                    return True
                elif protocol == 'socks4' and len(response) == 1 and response[0] == 0:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except:
                        pass
                    proxy['response_time_ms'] = elapsed
                    return True
                else:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except:
                        pass
                    return False
            else:
                # HTTP : test simple de connexion
                writer.close()
                try:
                    await writer.wait_closed()
                except:
                    pass
                proxy['response_time_ms'] = elapsed
                return True
                
        except asyncio.TimeoutError:
            return False
        except ConnectionRefusedError:
            return False
        except OSError:
            return False
        except Exception as e:
            logger.debug(f"Validation échouée {proxy.get('ip')}:{proxy.get('port')}: {e}")
            return False
    
    async def scrape_and_store(self):
        """Scrape les proxies de toutes les sources et les stocke en base"""
        logger.info("🚀 Début du scraping des proxies...")
        
        # Scraping parallèle de toutes les sources
        tasks = [
            self._scrape_geonode(),
            self._scrape_socks5_proxy(),
            self._scrape_spys_one(),
            self._scrape_proxyscrape(),
            self._scrape_openproxy(),
            self._scrape_free_proxy_list(),
            self._scrape_sockslist(),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(5) 
        # Fusionner tous les proxies
        all_proxies = []
        for result in results:
            if isinstance(result, list):
                all_proxies.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Erreur lors du scraping: {result}")
        
        # Déduplication
        seen = set()
        unique_proxies = []
        for p in all_proxies:
            key = (p.get('ip'), p.get('port'), p.get('protocol', 'socks5'))
            if key not in seen:
                seen.add(key)
                unique_proxies.append(p)
        
        logger.info(f"🌐 {len(unique_proxies)} proxies uniques après scraping")
        
        if not unique_proxies:
            logger.warning("⚠️ Aucun proxy trouvé, utilisation de proxies par défaut")
            # Proxies de secours (sources fiables)
            unique_proxies = self._get_fallback_proxies()
        
        # Validation parallèle (limitée à 50 à la fois pour éviter de saturer)
        valid_proxies = []
        batch_size = 50
        
        for i in range(0, len(unique_proxies), batch_size):
            batch = unique_proxies[i:i+batch_size]
            validation_tasks = [self._validate_proxy(p) for p in batch]
            validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
            
            for proxy, is_valid in zip(batch, validation_results):
                if is_valid is True:
                    valid_proxies.append(proxy)
            
            logger.info(f"✅ Validation batch {i//batch_size + 1}: {len([v for v in validation_results if v is True])}/{len(batch)} valides")
            await asyncio.sleep(0.5)  # Pause entre les batches
        
        logger.info(f"🔌 {len(valid_proxies)}/{len(unique_proxies)} proxies valides")
        
        # Stockage en base
        stored = self.db.add_proxies_batch(valid_proxies)
        
        # Marquer les invalides
        for proxy in unique_proxies:
            key = (proxy.get('ip'), proxy.get('port'), proxy.get('protocol', 'socks5'))
            if key not in {(p.get('ip'), p.get('port'), p.get('protocol', 'socks5')) for p in valid_proxies}:
                self.db.mark_proxy_invalid(proxy.get('ip'), proxy.get('port'))
        
        # Nettoyage des proxies invalides (garder seulement les valides récents)
        self.db.clear_invalid_proxies()
        
        logger.info(f"✅ Scraping terminé: {stored} proxies stockés")
        return stored
    
    def _get_fallback_proxies(self):
        """Proxies de secours quand le scraping échoue"""
        # Ces proxies sont des listes publiques connues, mais à vérifier
        fallback = [
            # SOCKS5 publics (listes courantes)
            {'ip': '51.158.68.68', 'port': 8811, 'protocol': 'socks5'},
            {'ip': '51.158.68.68', 'port': 8888, 'protocol': 'socks5'},
            {'ip': '163.172.151.224', 'port': 16379, 'protocol': 'socks5'},
            {'ip': '51.158.109.191', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.123.210', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.242.203', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.158.68.26', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.158.104.214', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.158.119.105', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.127.139', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.79.89', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.73.165', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.76.188', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.57.203', 'port': 1080, 'protocol': 'socks5'},
            # HTTP/HTTPS publics
            {'ip': '20.111.54.16', 'port': 8123, 'protocol': 'http'},
            {'ip': '20.111.54.17', 'port': 80, 'protocol': 'http'},
            {'ip': '20.210.113.32', 'port': 8123, 'protocol': 'http'},
            {'ip': '20.219.176.206', 'port': 3128, 'protocol': 'http'},
            {'ip': '20.44.189.178', 'port': 8080, 'protocol': 'http'},
            {'ip': '20.205.61.143', 'port': 80, 'protocol': 'http'},
            {'ip': '20.24.43.214', 'port': 8080, 'protocol': 'http'},
            {'ip': '20.219.177.108', 'port': 3128, 'protocol': 'http'},
            {'ip': '20.210.115.45', 'port': 3128, 'protocol': 'http'},
            {'ip': '20.111.54.18', 'port': 80, 'protocol': 'http'},
        ]
        return fallback
    
    async def scrape_quick(self):
        """Version rapide sans validation (juste collecte)"""
        logger.info("🚀 Scraping rapide...")
        
        tasks = [
            self._scrape_proxyscrape(),
            self._scrape_geonode(),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_proxies = []
        for result in results:
            if isinstance(result, list):
                all_proxies.extend(result)
        
        # Déduplication
        seen = set()
        unique = []
        for p in all_proxies:
            key = (p.get('ip'), p.get('port'), p.get('protocol', 'socks5'))
            if key not in seen:
                seen.add(key)
                unique.append(p)
        
        stored = self.db.add_proxies_batch(unique)
        logger.info(f"✅ Scraping rapide: {stored} proxies stockés")
        return storedimport asyncio
import aiohttp
import re
import logging
import random
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

class ProxyScraper:
    def __init__(self, db):
        self.db = db
        self.timeout = aiohttp.ClientTimeout(total=15)
        
        # User-Agents réalistes
        self.user_agents = [
            "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.165 Mobile Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 13; Pixel 9 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.159 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 14; Xiaomi 23127PN0CG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Mobile Safari/537.36",
        ]
    
    def _get_headers(self):
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    
    def _parse_proxy_string(self, line):
        """Parse une ligne de proxy au format ip:port ou protocol://ip:port"""
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('//'):
            return None
        
        protocol = "socks5"
        username = None
        password = None
        
        # Format: protocol://user:pass@ip:port
        match = re.match(r'(https?|socks4|socks5)://(?:(.+?):(.+?)@)?([\d.]+):(\d+)', line)
        if match:
            proto = match.group(1)
            if proto == 'socks4':
                protocol = 'socks4'
            elif proto == 'socks5':
                protocol = 'socks5'
            elif proto == 'http' or proto == 'https':
                protocol = 'http'
            username = match.group(2)
            password = match.group(3)
            ip = match.group(4)
            port = int(match.group(5))
            return {'ip': ip, 'port': port, 'protocol': protocol, 'username': username, 'password': password}
        
        # Format: ip:port
        match = re.match(r'([\d.]+):(\d+)', line)
        if match:
            return {'ip': match.group(1), 'port': int(match.group(2)), 'protocol': protocol}
        
        return None
    
    async def _fetch_url(self, url, source_name="unknown"):
        """Télécharge le contenu d'une URL avec gestion d'erreur"""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, headers=self._get_headers()) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        logger.debug(f"✅ {source_name}: {len(text)} bytes reçus")
                        return text
                    else:
                        logger.warning(f"⚠️ {source_name}: HTTP {resp.status}")
                        return None
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ {source_name}: Timeout")
            return None
        except Exception as e:
            logger.error(f"❌ {source_name}: {e}")
            return None
    
    async def _scrape_geonode(self):
        """Scrape proxies depuis GeoNode"""
        proxies = []
        for page in range(1, 4):
            url = f"https://proxylist.geonode.com/api/proxy-list?limit=100&page={page}&sort_by=lastChecked&sort_type=desc"
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.get(url, headers=self._get_headers()) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for p in data.get('data', []):
                                proxy = {
                                    'ip': p.get('ip'),
                                    'port': int(p.get('port', 0)),
                                    'protocol': p.get('protocols', ['socks5'])[0] if p.get('protocols') else 'socks5',
                                    'country': p.get('country'),
                                    'anonymity': p.get('anonymityLevel'),
                                    'response_time_ms': p.get('latency'),
                                }
                                if proxy['ip'] and proxy['port']:
                                    proxies.append(proxy)
            except Exception as e:
                logger.error(f"GeoNode page {page}: {e}")
                continue
        logger.info(f"GeoNode: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_socks5_proxy(self):
        """Scrape depuis socks5-proxy.net"""
        proxies = []
        url = "https://www.socks5-proxy.net/"
        text = await self._fetch_url(url, "socks5-proxy.net")
        if text:
            soup = BeautifulSoup(text, 'html.parser')
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')[1:]  # Skip header
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        ip = cols[0].get_text(strip=True)
                        port_text = cols[1].get_text(strip=True)
                        try:
                            port = int(port_text)
                            proxies.append({
                                'ip': ip,
                                'port': port,
                                'protocol': 'socks5',
                                'country': cols[3].get_text(strip=True) if len(cols) > 3 else None,
                            })
                        except ValueError:
                            continue
        logger.info(f"socks5-proxy.net: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_spys_one(self):
        """Scrape depuis spys.one"""
        proxies = []
        url = "https://spys.one/en/socks-proxy-list/"
        text = await self._fetch_url(url, "spys.one")
        if text:
            # Spys.one utilise des patterns spécifiques
            pattern = re.compile(r'(\d+\.\d+\.\d+\.\d+):(\d+)[^<]*<[^>]*>(\w+)')
            for match in pattern.finditer(text):
                proxies.append({
                    'ip': match.group(1),
                    'port': int(match.group(2)),
                    'protocol': 'socks5',
                    'country': match.group(3),
                })
        logger.info(f"spys.one: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_proxyscrape(self):
        """Scrape depuis proxyscrape.com (API)"""
        proxies = []
        urls = [
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all",
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&timeout=10000&country=all",
        ]
        
        for url in urls:
            protocol = 'socks5' if 'socks5' in url else ('socks4' if 'socks4' in url else 'http')
            text = await self._fetch_url(url, f"proxyscrape-{protocol}")
            if text:
                for line in text.split('\n'):
                    parsed = self._parse_proxy_string(line)
                    if parsed:
                        parsed['protocol'] = protocol
                        proxies.append(parsed)
        logger.info(f"proxyscrape: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_openproxy(self):
        """Scrape depuis openproxy.space"""
        proxies = []
        url = "https://openproxy.space/list/socks5"
        text = await self._fetch_url(url, "openproxy.space")
        if text:
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            ip = item.get('ip')
                            port = item.get('port')
                            if ip and port:
                                proxies.append({
                                    'ip': ip,
                                    'port': int(port),
                                    'protocol': 'socks5',
                                })
            except json.JSONDecodeError:
                # Fallback: format texte simple
                for line in text.split('\n'):
                    parsed = self._parse_proxy_string(line)
                    if parsed:
                        proxies.append(parsed)
        logger.info(f"openproxy.space: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_free_proxy_list(self):
        """Scrape depuis free-proxy-list.net"""
        proxies = []
        url = "https://free-proxy-list.net/"
        text = await self._fetch_url(url, "free-proxy-list.net")
        if text:
            soup = BeautifulSoup(text, 'html.parser')
            table = soup.find('table', class_='table')
            if table:
                rows = table.find_all('tr')[1:]
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        ip = cols[0].get_text(strip=True)
                        port = cols[1].get_text(strip=True)
                        try:
                            proxies.append({
                                'ip': ip,
                                'port': int(port),
                                'protocol': 'http',
                                'country': cols[3].get_text(strip=True) if len(cols) > 3 else None,
                                'anonymity': cols[4].get_text(strip=True) if len(cols) > 4 else None,
                            })
                        except ValueError:
                            continue
        logger.info(f"free-proxy-list.net: {len(proxies)} proxies")
        return proxies
    
    async def _scrape_sockslist(self):
        """Scrape depuis sockslist.net"""
        proxies = []
        url = "https://sockslist.net/list/socks5/1"
        text = await self._fetch_url(url, "sockslist.net")
        if text:
            soup = BeautifulSoup(text, 'html.parser')
            # Chercher les adresses IP dans le contenu
            pattern = re.compile(r'(\d+\.\d+\.\d+\.\d+)[:\s]+(\d+)')
            for match in pattern.finditer(text):
                proxies.append({
                    'ip': match.group(1),
                    'port': int(match.group(2)),
                    'protocol': 'socks5',
                })
        logger.info(f"sockslist.net: {len(proxies)} proxies")
        return proxies
    
    async def _validate_proxy(self, proxy):
        """Valide un proxy en testant la connexion TCP et SOCKS5"""
        try:
            ip = proxy['ip']
            port = proxy['port']
            protocol = proxy.get('protocol', 'socks5')
            
            # Test TCP de base
            start = asyncio.get_event_loop().time()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=8
            )
            elapsed = int((asyncio.get_event_loop().time() - start) * 1000)
            
            # Test SOCKS5 handshake si c'est un proxy SOCKS
            if protocol in ('socks5', 'socks4'):
                # Envoi du handshake SOCKS5
                if protocol == 'socks5':
                    writer.write(b'\x05\x01\x00')  # SOCKS5, 1 auth method, no auth
                else:
                    writer.write(b'\x04\x01\x00\x50\x00\x00\x00\x00\x00\x00\x00\x00')  # SOCKS4
                await writer.drain()
                response = await asyncio.wait_for(reader.read(2), timeout=5)
                
                if protocol == 'socks5' and len(response) == 2 and response[0] == 5:
                    # Handshake SOCKS5 réussi
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except:
                        pass
                    proxy['response_time_ms'] = elapsed
                    return True
                elif protocol == 'socks4' and len(response) == 1 and response[0] == 0:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except:
                        pass
                    proxy['response_time_ms'] = elapsed
                    return True
                else:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except:
                        pass
                    return False
            else:
                # HTTP : test simple de connexion
                writer.close()
                try:
                    await writer.wait_closed()
                except:
                    pass
                proxy['response_time_ms'] = elapsed
                return True
                
        except asyncio.TimeoutError:
            return False
        except ConnectionRefusedError:
            return False
        except OSError:
            return False
        except Exception as e:
            logger.debug(f"Validation échouée {proxy.get('ip')}:{proxy.get('port')}: {e}")
            return False
    
    async def scrape_and_store(self):
        """Scrape les proxies de toutes les sources et les stocke en base"""
        logger.info("🚀 Début du scraping des proxies...")
        
        # Scraping parallèle de toutes les sources
        tasks = [
            self._scrape_geonode(),
            self._scrape_socks5_proxy(),
            self._scrape_spys_one(),
            self._scrape_proxyscrape(),
            self._scrape_openproxy(),
            self._scrape_free_proxy_list(),
            self._scrape_sockslist(),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Fusionner tous les proxies
        all_proxies = []
        for result in results:
            if isinstance(result, list):
                all_proxies.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Erreur lors du scraping: {result}")
        
        # Déduplication
        seen = set()
        unique_proxies = []
        for p in all_proxies:
            key = (p.get('ip'), p.get('port'), p.get('protocol', 'socks5'))
            if key not in seen:
                seen.add(key)
                unique_proxies.append(p)
        
        logger.info(f"🌐 {len(unique_proxies)} proxies uniques après scraping")
        
        if not unique_proxies:
            logger.warning("⚠️ Aucun proxy trouvé, utilisation de proxies par défaut")
            # Proxies de secours (sources fiables)
            unique_proxies = self._get_fallback_proxies()
        
        # Validation parallèle (limitée à 50 à la fois pour éviter de saturer)
        valid_proxies = []
        batch_size = 50
        
        for i in range(0, len(unique_proxies), batch_size):
            batch = unique_proxies[i:i+batch_size]
            validation_tasks = [self._validate_proxy(p) for p in batch]
            validation_results = await asyncio.gather(*validation_tasks, return_exceptions=True)
            
            for proxy, is_valid in zip(batch, validation_results):
                if is_valid is True:
                    valid_proxies.append(proxy)
            
            logger.info(f"✅ Validation batch {i//batch_size + 1}: {len([v for v in validation_results if v is True])}/{len(batch)} valides")
            await asyncio.sleep(0.5)  # Pause entre les batches
        
        logger.info(f"🔌 {len(valid_proxies)}/{len(unique_proxies)} proxies valides")
        
        # Stockage en base
        stored = self.db.add_proxies_batch(valid_proxies)
        
        # Marquer les invalides
        for proxy in unique_proxies:
            key = (proxy.get('ip'), proxy.get('port'), proxy.get('protocol', 'socks5'))
            if key not in {(p.get('ip'), p.get('port'), p.get('protocol', 'socks5')) for p in valid_proxies}:
                self.db.mark_proxy_invalid(proxy.get('ip'), proxy.get('port'))
        
        # Nettoyage des proxies invalides (garder seulement les valides récents)
        self.db.clear_invalid_proxies()
        
        logger.info(f"✅ Scraping terminé: {stored} proxies stockés")
        return stored
    
    def _get_fallback_proxies(self):
        """Proxies de secours quand le scraping échoue"""
        # Ces proxies sont des listes publiques connues, mais à vérifier
        fallback = [
            # SOCKS5 publics (listes courantes)
            {'ip': '51.158.68.68', 'port': 8811, 'protocol': 'socks5'},
            {'ip': '51.158.68.68', 'port': 8888, 'protocol': 'socks5'},
            {'ip': '163.172.151.224', 'port': 16379, 'protocol': 'socks5'},
            {'ip': '51.158.109.191', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.123.210', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.242.203', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.158.68.26', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.158.104.214', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.158.119.105', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.127.139', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.79.89', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.73.165', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.76.188', 'port': 1080, 'protocol': 'socks5'},
            {'ip': '51.15.57.203', 'port': 1080, 'protocol': 'socks5'},
            # HTTP/HTTPS publics
            {'ip': '20.111.54.16', 'port': 8123, 'protocol': 'http'},
            {'ip': '20.111.54.17', 'port': 80, 'protocol': 'http'},
            {'ip': '20.210.113.32', 'port': 8123, 'protocol': 'http'},
            {'ip': '20.219.176.206', 'port': 3128, 'protocol': 'http'},
            {'ip': '20.44.189.178', 'port': 8080, 'protocol': 'http'},
            {'ip': '20.205.61.143', 'port': 80, 'protocol': 'http'},
            {'ip': '20.24.43.214', 'port': 8080, 'protocol': 'http'},
            {'ip': '20.219.177.108', 'port': 3128, 'protocol': 'http'},
            {'ip': '20.210.115.45', 'port': 3128, 'protocol': 'http'},
            {'ip': '20.111.54.18', 'port': 80, 'protocol': 'http'},
        ]
        return fallback
    
    async def scrape_quick(self):
        """Version rapide sans validation (juste collecte)"""
        logger.info("🚀 Scraping rapide...")
        
        tasks = [
            self._scrape_proxyscrape(),
            self._scrape_geonode(),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_proxies = []
        for result in results:
            if isinstance(result, list):
                all_proxies.extend(result)
        
        # Déduplication
        seen = set()
        unique = []
        for p in all_proxies:
            key = (p.get('ip'), p.get('port'), p.get('protocol', 'socks5'))
            if key not in seen:
                seen.add(key)
                unique.append(p)
        
        stored = self.db.add_proxies_batch(unique)
        logger.info(f"✅ Scraping rapide: {stored} proxies stockés")
        return stored
