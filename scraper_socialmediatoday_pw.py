#!/usr/bin/env python3
import json
import asyncio
from datetime import datetime, timezone, date, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth

TOPICS = [
    ("https://www.socialmediatoday.com/topic/instagram/", "social", True),
    ("https://www.socialmediatoday.com/topic/facebook/",  "social", True),
    ("https://www.socialmediatoday.com/topic/snapchat/",  "social", True),
    ("https://www.socialmediatoday.com/topic/pinterest/", "photo-text", True),
    ("https://www.socialmediatoday.com/topic/twitter/",   "photo-text", True),
]

def parse_smt_date(date_str):
    date_str_lower = date_str.lower().strip() if date_str else ""
    if any(x in date_str_lower for x in ["hour", "minute", "just now"]):
        return True, date.today().strftime("%Y-%m-%d")
    if "1 day ago" in date_str_lower or "yesterday" in date_str_lower:
        return True, (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        dt = datetime.strptime(date_str_lower, "%B %d, %Y")
        article_date_str = dt.strftime("%Y-%m-%d")
        today = date.today().strftime("%Y-%m-%d")
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return article_date_str in [today, yesterday], article_date_str
    except:
        pass
    return False, date_str

async def fetch_topic(browser, url, category, is_priority):
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    # 修正调用
    await stealth(page)
    
    print(f"  [SocialMediaToday] Visiting {url} ...")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        title = await page.title()
        if "Attention Required" in title or "blocked" in title.lower():
            print(f"  [Error] Blocked by Cloudflare on {url}")
            return []
            
        items = await page.query_selector_all("li.feed__item")
        results = []
        for item in items:
            title_el = await item.query_selector("h3.feed__title a")
            if not title_el: continue
            title_text = await title_el.inner_text()
            href = await title_el.get_attribute("href")
            link = "https://www.socialmediatoday.com" + href if href.startswith("/") else href
            date_el = await item.query_selector("span.feed__date")
            date_text = await date_el.inner_text() if date_el else ""
            is_recent, parsed_date = parse_smt_date(date_text)
            if is_recent:
                results.append({
                    "source": "Social Media Today",
                    "title": title_text.strip(),
                    "summary": title_text.strip(),
                    "url": link,
                    "date": parsed_date,
                    "category": category,
                    "is_priority": is_priority
                })
        return results
    except Exception as e:
        print(f"  [Error] {url}: {e}")
        return []
    finally:
        await page.close()
        await context.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        all_items = []
        seen_urls = set()
        for url, category, is_priority in TOPICS:
            items = await fetch_topic(browser, url, category, is_priority)
            for it in items:
                if it["url"] not in seen_urls:
                    seen_urls.add(it["url"])
                    all_items.append(it)
            print(f"    Found {len(items)} items")
            await asyncio.sleep(1)
        await browser.close()
        
        output = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": "Social Media Today",
            "items": all_items
        }
        with open("socialmediatoday_raw.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
