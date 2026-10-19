import asyncio
import aiohttp
import aiofiles
import hashlib
import json
import logging
import os
import re
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup
import urllib.robotparser
from playwright.async_api import async_playwright
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

def sanitize_filename(filename):
    """Decode URL-encoded filename and make it valid for Windows."""
    decoded = unquote(filename)
    # Windows invalid characters: < > : " / \ | ? *
    return re.sub(r'[<>:"/\\|?*]', '_', decoded)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# Configuration
MANIFEST_FILE = "manifest.json"
DATA_DIR_AGRI = os.path.join(".", "data", "agriwelfare")
DATA_DIR_KRISHI = os.path.join(".", "data", "krishi")

# Make sure directories exist
os.makedirs(DATA_DIR_AGRI, exist_ok=True)
os.makedirs(DATA_DIR_KRISHI, exist_ok=True)

class ScraperState:
    def __init__(self):
        self.visited_urls = []
        self.downloaded_hashes = []
        self.load_state()

    def load_state(self):
        if os.path.exists(MANIFEST_FILE):
            try:
                with open(MANIFEST_FILE, "r") as f:
                    data = json.load(f)
                    self.visited_urls = data.get("visited_urls", [])
                    self.downloaded_hashes = data.get("downloaded_hashes", [])
            except json.JSONDecodeError:
                logging.error(f"Error parsing {MANIFEST_FILE}, starting with empty state.")

    def save_state(self):
        data = {
            "visited_urls": self.visited_urls,
            "downloaded_hashes": self.downloaded_hashes
        }
        with open(MANIFEST_FILE, "w") as f:
            json.dump(data, f, indent=4)

    def add_visited(self, url):
        if url not in self.visited_urls:
            self.visited_urls.append(url)
            self.save_state()

    def is_visited(self, url):
        return url in self.visited_urls

    def add_hash(self, file_hash):
        if file_hash not in self.downloaded_hashes:
            self.downloaded_hashes.append(file_hash)
            self.save_state()

    def is_downloaded(self, file_hash):
        return file_hash in self.downloaded_hashes

async def calculate_hash(file_path):
    sha256_hash = hashlib.sha256()
    async with aiofiles.open(file_path, "rb") as f:
        while chunk := await f.read(8192):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

class AgriwelfareCrawler:
    def __init__(self, state: ScraperState):
        self.state = state
        self.start_url = "https://www.agriwelfare.gov.in/en/"
        self.allowed_domain = "agriwelfare.gov.in"
        self.max_depth = 3
        self.allowed_extensions = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
        self.ignored_extensions = {".jpg", ".png", ".svg", ".css", ".js"}
        self.max_retries = 3
        self.concurrency = 10
        self.semaphore = asyncio.Semaphore(self.concurrency)
        self.downloaded_count = 0
        self.max_downloads = 100
        self.lock = asyncio.Lock()
        
        self.rp = urllib.robotparser.RobotFileParser()
        self.rp.set_url(f"https://{self.allowed_domain}/robots.txt")
        try:
            self.rp.read()
            logging.info("robots.txt loaded successfully for agriwelfare.")
        except Exception as e:
            logging.warning(f"Could not load robots.txt: {e}")
            self.rp = None
            
        self.priority_patterns = [
            re.compile(r"/Documents/"),
            re.compile(r"/Downloads/"),
            re.compile(r"/Reports/")
        ]
        
        self.session_visited_pages = set()

    def is_allowed_by_robots(self, url):
        if self.rp:
            allowed = self.rp.can_fetch("*", url)
            if not allowed:
                logging.debug(f"[DEBUG] BLOCKED by robots.txt: {url}")
            return allowed
        return True

    def get_extension(self, url):
        path = urlparse(url).path
        _, ext = os.path.splitext(path)
        return ext.lower()

    def is_valid_url(self, url):
        parsed = urlparse(url)
        if parsed.netloc != self.allowed_domain and not parsed.netloc.endswith(f".{self.allowed_domain}"):
            logging.debug(f"[DEBUG] REJECTED (wrong domain): {parsed.netloc} | URL: {url}")
            return False
        ext = self.get_extension(url)
        if ext in self.ignored_extensions:
            return False
        lower_url = url.lower()
        if any(keyword in lower_url for keyword in ["login", "admin", "logout"]):
            logging.debug(f"[DEBUG] REJECTED (blocked keyword): {url}")
            return False
        return True

    def get_category_and_filename(self, url):
        parsed = urlparse(url)
        path_parts = [p for p in unquote(parsed.path).split('/') if p]
        if not path_parts:
            return "root", "unknown"
        original_filename = path_parts[-1]
        section = "default"
        if len(path_parts) > 1:
            section = path_parts[-2]
            section = re.sub(r'[^a-zA-Z0-9_\-]', '', section)
        if not section:
            section = "default"
        return section, original_filename

    async def download_file(self, session, url):
        if self.downloaded_count >= self.max_downloads:
            return
        if self.state.is_visited(url):
            return
        
        self.state.add_visited(url)
        
        section, original_filename = self.get_category_and_filename(url)
        clean_filename = sanitize_filename(original_filename)
        final_filename = f"{section}_{clean_filename}"
        
        local_path = os.path.join(DATA_DIR_AGRI, final_filename)

        async with self.semaphore:
            if self.downloaded_count >= self.max_downloads:
                return
            for attempt in range(1, self.max_retries + 1):
                try:
                    logging.info(f"Downloading [Agriwelfare]: {url}")
                    async with session.get(url, timeout=30) as response:
                        response.raise_for_status()
                        
                        content_length = response.headers.get('Content-Length')
                        if content_length and int(content_length) > 10 * 1024 * 1024:
                            logging.info(f"File too large (>10MB), skipping: {url}")
                            return
                            
                        tmp_path = local_path + ".tmp"
                        downloaded_size = 0
                        async with aiofiles.open(tmp_path, "wb") as f:
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                downloaded_size += len(chunk)
                                if downloaded_size > 10 * 1024 * 1024:
                                    break
                                await f.write(chunk)
                                
                        if downloaded_size > 10 * 1024 * 1024:
                            logging.info(f"File exceeded 10MB during download, aborting: {url}")
                            os.remove(tmp_path)
                            return
                                
                        file_hash = await calculate_hash(tmp_path)
                        if self.state.is_downloaded(file_hash):
                            logging.info(f"Duplicate file found, skipping: {url}")
                            os.remove(tmp_path)
                            async with self.lock:
                                self.downloaded_count += 1
                            return
                            
                        self.state.add_hash(file_hash)
                        os.rename(tmp_path, local_path)
                        async with self.lock:
                            self.downloaded_count += 1
                        logging.info(f"Successfully downloaded: {local_path} ({self.downloaded_count}/{self.max_downloads})")
                        return 
                except Exception as e:
                    logging.error(f"Error downloading {url}: {e}")
                    await asyncio.sleep(2)

    async def crawl_page(self, session, url, depth, priority_queue):
        if self.downloaded_count >= self.max_downloads:
            logging.info(f"[DEBUG] Max downloads reached ({self.max_downloads}), stopping.")
            return
        if depth > self.max_depth:
            logging.debug(f"[DEBUG] Max depth ({self.max_depth}) exceeded for: {url}")
            return
        if self.state.is_visited(url):
            return
            
        if not self.is_allowed_by_robots(url):
            return
            
        self.state.add_visited(url)
        logging.info(f"[DEBUG] Crawling page (depth={depth}): {url}")
        
        async with self.semaphore:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        logging.warning(f"[DEBUG] Non-200 status ({response.status}) for: {url}")
                        return
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "text/html" not in content_type:
                        logging.debug(f"[DEBUG] Non-HTML content-type ({content_type}) for: {url}")
                        return
                    html = await response.text()
                    logging.info(f"[DEBUG] Page loaded successfully, HTML length: {len(html)} chars")
            except Exception as e:
                logging.error(f"[DEBUG] Failed to fetch page {url}: {e}")
                return
                
        soup = BeautifulSoup(html, "html.parser")
        all_links = soup.find_all("a", href=True)
        logging.info(f"[DEBUG] Found {len(all_links)} total <a> tags on page: {url}")
        
        tasks = []
        downloadable_links = 0
        page_links = 0
        rejected_links = 0
        
        for a_tag in all_links:
            href = a_tag["href"]
            next_url = urljoin(url, href)
            next_url = urlparse(next_url)._replace(fragment="").geturl()
            
            if not self.is_valid_url(next_url):
                rejected_links += 1
                continue
                
            ext = self.get_extension(next_url)
            if ext in self.allowed_extensions:
                downloadable_links += 1
                logging.info(f"[DEBUG] Found downloadable file ({ext}): {next_url}")
                tasks.append(self.download_file(session, next_url))
            elif ext in ["", ".html", ".htm", ".php", ".aspx"]:
                if not self.state.is_visited(next_url):
                    page_links += 1
                    priority = 1
                    if any(p.search(next_url) for p in self.priority_patterns):
                        priority = 0
                    priority_queue.put_nowait((priority, depth + 1, next_url))
        
        logging.info(f"[DEBUG] Link summary for {url}: {downloadable_links} downloadable, {page_links} pages queued, {rejected_links} rejected")
                    
        if tasks:
            await asyncio.gather(*tasks)

    async def run(self):
        logging.info("Starting Agriwelfare Crawler...")
        logging.info(f"[DEBUG] Config: max_depth={self.max_depth}, max_downloads={self.max_downloads}, concurrency={self.concurrency}")
        logging.info(f"[DEBUG] Start URL: {self.start_url}")
        logging.info(f"[DEBUG] Allowed extensions: {self.allowed_extensions}")
        priority_queue = asyncio.PriorityQueue()
        priority_queue.put_nowait((0, 0, self.start_url))
        
        connector = aiohttp.TCPConnector(limit=self.concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            async def worker():
                while True:
                    try:
                        priority, depth, current_url = await priority_queue.get()
                    except asyncio.CancelledError:
                        break
                        
                    try:
                        await self.crawl_page(session, current_url, depth, priority_queue)
                    except Exception as e:
                        logging.error(f"Worker error: {e}")
                    finally:
                        priority_queue.task_done()
                        
            workers = [asyncio.create_task(worker()) for _ in range(self.concurrency)]
            await priority_queue.join()
            for w in workers:
                w.cancel()
        logging.info(f"Agriwelfare Crawler finished. Total downloaded: {self.downloaded_count}")
        logging.info(f"[DEBUG] Total URLs visited: {len(self.state.visited_urls)}")

class KrishiCrawler:
    def __init__(self, state: ScraperState):
        self.state = state
        self.downloaded_count = 0
        self.max_downloads = 100
        self.lock = asyncio.Lock()

    async def run(self):
        logging.info("Starting Krishi Maharashtra Crawler...")
        pdf_links = set()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                target_url = "https://krishi.maharashtra.gov.in/"
                logging.info(f"[DEBUG] Krishi: Navigating to {target_url}")
                await page.goto(target_url, timeout=60000)
                logging.info(f"[DEBUG] Krishi: Page loaded, waiting 5s for JS rendering...")
                await page.wait_for_timeout(5000)
                
                logging.info(f"[DEBUG] Krishi: Page title: {await page.title()}")
                logging.info(f"[DEBUG] Krishi: Current URL: {page.url}")

                links = await page.eval_on_selector_all(
                    "a",
                    "elements => elements.map(e => e.href)"
                )
                logging.info(f"[DEBUG] Krishi: Found {len(links)} total <a> tags on page")
                
                # Log first 10 links for debugging
                for i, link in enumerate(links[:10]):
                    logging.info(f"[DEBUG] Krishi: Sample link [{i}]: {link}")

                for link in links:
                    if link and "pdf" in link.lower():
                        pdf_links.add(link)
                        
                logging.info(f"[DEBUG] Krishi: Found {len(pdf_links)} PDF links")
                for pdf_link in pdf_links:
                    logging.info(f"[DEBUG] Krishi PDF: {pdf_link}")
                    
            except Exception as e:
                logging.error(f"Error loading Krishi page: {e}")
                import traceback
                logging.error(f"[DEBUG] Krishi traceback: {traceback.format_exc()}")
            finally:
                await browser.close()

        logging.info(f"[DEBUG] Krishi: Proceeding to download {len(pdf_links)} PDFs...")
        async with aiohttp.ClientSession() as session:
            tasks = [self.download_file(session, url) for url in pdf_links]
            if tasks:
                await asyncio.gather(*tasks)
        logging.info(f"Krishi Maharashtra Crawler finished. Total downloaded: {self.downloaded_count}")

    async def download_file(self, session, url):
        if self.downloaded_count >= self.max_downloads:
            return
        if self.state.is_visited(url):
            return
            
        try:
            filename = url.split("/")[-1].split("?")[0]
            filename = sanitize_filename(filename)
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"
            path = os.path.join(DATA_DIR_KRISHI, filename)

            async with session.get(url) as resp:
                if resp.status == 200:
                    content_length = resp.headers.get('Content-Length')
                    if content_length and int(content_length) > 10 * 1024 * 1024:
                        logging.info(f"File too large (>10MB), skipping: {url}")
                        return
                        
                    tmp_path = path + ".tmp"
                    downloaded_size = 0
                    async with aiofiles.open(tmp_path, "wb") as f:
                        while True:
                            chunk = await resp.content.read(8192)
                            if not chunk:
                                break
                            downloaded_size += len(chunk)
                            if downloaded_size > 10 * 1024 * 1024:
                                break
                            await f.write(chunk)
                            
                    if downloaded_size > 10 * 1024 * 1024:
                        logging.info(f"File exceeded 10MB during download, aborting: {url}")
                        os.remove(tmp_path)
                        return
                    
                    file_hash = await calculate_hash(tmp_path)
                    if self.state.is_downloaded(file_hash):
                        logging.info(f"Duplicate file found, skipping: {url}")
                        os.remove(tmp_path)
                        async with self.lock:
                            self.downloaded_count += 1
                    else:
                        self.state.add_hash(file_hash)
                        self.state.add_visited(url)
                        os.rename(tmp_path, path)
                        async with self.lock:
                            self.downloaded_count += 1
                        logging.info(f"Successfully downloaded [Krishi]: {filename} ({self.downloaded_count}/{self.max_downloads})")
        except Exception as e:
            logging.error(f"Error downloading {url}: {e}")

async def run_all_crawlers():
    state = ScraperState()
    agri_crawler = AgriwelfareCrawler(state)
    krishi_crawler = KrishiCrawler(state)
    
    await asyncio.gather(
        agri_crawler.run(),
        krishi_crawler.run()
    )

def run_scrapers_sync():
    """Wrapper to run the async scrapers from a synchronous scheduler."""
    logging.info("Starting scheduled scraping job...")
    asyncio.run(run_all_crawlers())
    logging.info("Scheduled scraping job finished.")

def start_scheduler():
    scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Kolkata'))
    scheduler.add_job(run_scrapers_sync, 'cron', hour=23, minute=0)
    scheduler.start()
    logging.info("Scheduler started. Jobs will run daily at 11:00 PM IST.")

if __name__ == "__main__":
    run_scrapers_sync()
