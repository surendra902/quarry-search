import asyncio
import json
import os
from playwright.async_api import async_playwright

async def search_reddit_live():
    evidence_dir = os.path.join(os.path.dirname(__file__), "evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    query = "PFQOnxQmRQ"
    search_url = f"https://www.reddit.com/search/?q={query}&sort=new"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        print(f"Navigating to Reddit search: {search_url}")
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(4)
        except Exception as e:
            print(f"Error navigating: {e}")
            
        screenshot_path = os.path.join(evidence_dir, "reddit_search_result.png")
        await page.screenshot(path=screenshot_path)
        
        text = await page.evaluate("() => document.body.innerText")
        print(f"Reddit search text preview (first 500 chars):\n{text[:500]}")
        
        has_results = "Hm... we couldn't find any results" not in text and "No results" not in text
        print(f"Has results: {has_results}")
        
        with open(os.path.join(evidence_dir, "reddit_search_text.txt"), "w", encoding="utf-8") as f:
            f.write(text)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(search_reddit_live())
