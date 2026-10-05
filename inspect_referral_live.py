import asyncio
import json
import os
from playwright.async_api import async_playwright

async def inspect_target():
    evidence_dir = os.path.join(os.path.dirname(__file__), "evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    target_url = "https://claude.ai/referral/PFQOnxQmRQ"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        
        responses = []
        page.on("response", lambda r: responses.append({
            "url": r.url,
            "status": r.status,
            "headers": dict(r.headers)
        }))
        
        print(f"Navigating to {target_url}...")
        try:
            resp = await page.goto(target_url, wait_until="networkidle", timeout=30000)
            status = resp.status if resp else "no_response"
        except Exception as e:
            print(f"Navigation note: {e}")
            status = "timeout_or_error"
            
        await asyncio.sleep(3)
        
        final_url = page.url
        title = await page.title()
        content = await page.content()
        text = await page.evaluate("() => document.body.innerText")
        
        screenshot_path = os.path.join(evidence_dir, "claude_referral_page.png")
        await page.screenshot(path=screenshot_path, full_page=True)
        
        result = {
            "initial_url": target_url,
            "final_url": final_url,
            "title": title,
            "body_text": text,
            "screenshot": screenshot_path,
            "html_length": len(content),
            "relevant_responses": [r for r in responses if "claude.ai" in r["url"] or "referral" in r["url"]][:20]
        }
        
        with open(os.path.join(evidence_dir, "playwright_referral_result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            
        print(f"Title: {title}")
        print(f"Final URL: {final_url}")
        print(f"Body text sample (first 400 chars):\n{text[:400]}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_target())
