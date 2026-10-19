import asyncio
from playwright.async_api import async_playwright
import os
import aiohttp
import aiofiles

DATA_DIR = "./data/krishi"
os.makedirs(DATA_DIR, exist_ok=True)

async def download_file(session, url):
    try:
        filename = url.split("/")[-1].split("?")[0]
        path = os.path.join(DATA_DIR, filename)

        async with session.get(url) as resp:
            if resp.status == 200:
                async with aiofiles.open(path, "wb") as f:
                    await f.write(await resp.read())
                print(f"Downloaded: {filename}")
    except:
        pass

async def main():
    pdf_links = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://krishi.maharashtra.gov.in/", timeout=60000)
        await page.wait_for_timeout(5000)

        links = await page.eval_on_selector_all(
            "a",
            "elements => elements.map(e => e.href)"
        )

        for link in links:
            if link and "pdf" in link.lower():
                pdf_links.add(link)

        await browser.close()

    async with aiohttp.ClientSession() as session:
        tasks = [download_file(session, url) for url in pdf_links]
        await asyncio.gather(*tasks)

    print(f"Total PDFs: {len(pdf_links)}")

if __name__ == "__main__":
    asyncio.run(main())