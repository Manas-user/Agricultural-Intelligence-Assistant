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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

START_URL = "https://www.agriwelfare.gov.in/en/"
ALLOWED_DOMAIN = "agriwelfare.gov.in"
MAX_DEPTH = 3
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx"}
IGNORED_EXTENSIONS = {".jpg", ".png", ".svg", ".css", ".js"}
MAX_RETRIES = 3
CONCURRENCY = 10
DATA_DIR = os.path.join(".", "data", "agriwelfare")

class AgriwelfareCrawler:
    def __init__(self):
        self.visited_urls = set()
        self.downloaded_hashes = set()
        self.documents = []  
        self.total_pages_crawled = 0
        self.semaphore = asyncio.Semaphore(CONCURRENCY)
        
        self.rp = urllib.robotparser.RobotFileParser()
        self.rp.set_url(f"https://{ALLOWED_DOMAIN}/robots.txt")
        try:
            self.rp.read()
            logging.info("robots.txt loaded successfully.")
        except Exception as e:
            logging.warning(f"Could not load robots.txt: {e}")
            self.rp = None
            
        self.priority_patterns = [
            re.compile(r"/Documents/"),
            re.compile(r"/Downloads/"),
            re.compile(r"/Reports/")
        ]

    def is_allowed_by_robots(self, url):
        if self.rp:
            return self.rp.can_fetch("*", url)
        return True

    def get_extension(self, url):
        path = urlparse(url).path
        _, ext = os.path.splitext(path)
        return ext.lower()

    def is_valid_url(self, url):
        parsed = urlparse(url)
        if parsed.netloc != ALLOWED_DOMAIN and not parsed.netloc.endswith(f".{ALLOWED_DOMAIN}"):
            return False
            
        ext = self.get_extension(url)
        if ext in IGNORED_EXTENSIONS:
            return False
            
        lower_url = url.lower()
        if any(keyword in lower_url for keyword in ["login", "admin", "logout"]):
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

    async def calculate_hash(self, file_path):
        sha256_hash = hashlib.sha256()
        async with aiofiles.open(file_path, "rb") as f:
            while chunk := await f.read(8192):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    async def download_file(self, session, url, source_page):
        if url in self.visited_urls:
            return
            
        self.visited_urls.add(url)
        
        ext = self.get_extension(url)
        section, original_filename = self.get_category_and_filename(url)
        
        # Clean filename
        clean_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', original_filename)
        final_filename = f"{section}_{clean_filename}"
        
        local_path = os.path.join(DATA_DIR, final_filename)

        async with self.semaphore:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    logging.info(f"Downloading Document [{attempt}/{MAX_RETRIES}]: {url}")
                    async with session.get(url, timeout=30) as response:
                        response.raise_for_status()
                        
                        tmp_path = local_path + ".tmp"
                        async with aiofiles.open(tmp_path, "wb") as f:
                            while True:
                                chunk = await response.content.read(8192)
                                if not chunk:
                                    break
                                await f.write(chunk)
                                
                        file_hash = await self.calculate_hash(tmp_path)
                        if file_hash in self.downloaded_hashes:
                            logging.info(f"Duplicate file found, skipping: {url}")
                            os.remove(tmp_path)
                            return
                            
                        self.downloaded_hashes.add(file_hash)
                        os.rename(tmp_path, local_path)
                        logging.info(f"Successfully downloaded: {local_path}")
                        
                        self.documents.append({
                            "url": url,
                            "file_type": ext.strip("."),
                            "local_path": local_path,
                            "source_page": source_page
                        })
                        return 
                except Exception as e:
                    logging.error(f"Error downloading {url} (Attempt {attempt}): {e}")
                    if attempt == MAX_RETRIES:
                        logging.error(f"Failed to download {url} after {MAX_RETRIES} attempts.")
                    await asyncio.sleep(2)

    async def crawl_page(self, session, url, depth, priority_queue):
        if depth > MAX_DEPTH:
            return
            
        if url in self.visited_urls:
            return
            
        if not self.is_allowed_by_robots(url):
            logging.info(f"Skipped by robots.txt: {url}")
            return
            
        self.visited_urls.add(url)
        self.total_pages_crawled += 1
        
        async with self.semaphore:
            logging.info(f"Crawling (Depth {depth}): {url}")
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
                }
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        logging.warning(f"HTTP Error {response.status} for {url}")
                        return
                    
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "text/html" not in content_type:
                        return
                    
                    html = await response.text()
            except Exception as e:
                logging.error(f"Error crawling {url}: {e}")
                return
                
        soup = BeautifulSoup(html, "html.parser")
        
        tasks = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            next_url = urljoin(url, href)
            
            next_url = urlparse(next_url)._replace(fragment="").geturl()
            
            if not self.is_valid_url(next_url):
                continue
                
            ext = self.get_extension(next_url)
            
            if ext in ALLOWED_EXTENSIONS:
                tasks.append(self.download_file(session, next_url, url))
            elif ext == "" or ext == ".html" or ext == ".htm" or ext == ".php" or ext == ".aspx":
                if next_url not in self.visited_urls:
                    priority = 1
                    if any(p.search(next_url) for p in self.priority_patterns):
                        priority = 0
                    
                    priority_queue.put_nowait((priority, depth + 1, next_url))
                    
        if tasks:
            await asyncio.gather(*tasks)

    async def run(self):
        logging.info("Starting crawler...")
        os.makedirs(DATA_DIR, exist_ok=True)
        
        priority_queue = asyncio.PriorityQueue()
        priority_queue.put_nowait((0, 0, START_URL))
        
        connector = aiohttp.TCPConnector(limit=CONCURRENCY)
        async with aiohttp.ClientSession(connector=connector) as session:
            async def worker():
                while True:
                    try:
                        priority, depth, current_url = await priority_queue.get()
                        await self.crawl_page(session, current_url, depth, priority_queue)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logging.error(f"Worker error: {e}")
                    finally:
                        priority_queue.task_done()
                        
            workers = [asyncio.create_task(worker()) for _ in range(CONCURRENCY)]
            
            await priority_queue.join()
            
            for w in workers:
                w.cancel()
            
        result = {
            "total_pages_crawled": self.total_pages_crawled,
            "total_documents_found": len(self.documents),
            "documents": self.documents
        }
        
        output_file = "results.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4)
            
        logging.info("Crawler finished.")
        logging.info(f"Total pages crawled: {self.total_pages_crawled}")
        logging.info(f"Total documents found: {len(self.documents)}")
        logging.info(f"Detailed results saved to {output_file}")

if __name__ == "__main__":
    crawler = AgriwelfareCrawler()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        task = loop.create_task(crawler.run())
    else:
        asyncio.run(crawler.run())
