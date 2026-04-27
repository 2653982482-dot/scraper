#!/usr/bin/env python3
import json
import asyncio
from datetime import datetime, timezone, date, timedelta
from playwright.async_api import async_playwright
try:
    # 尝试多种可能的导入方式
    import playwright_stealth
    def apply_stealth(page):
        # 2.0.2 版本通常是 playwright_stealth.stealth(page)
        # 注意：它是同步函数，不需要 await
        try:
            playwright_stealth.stealth(page)
        except:
            pass
except ImportError:
    apply_stealth = lambda x: None

SMT_TOPICS = [
    ("https://www.socialmediatoday.com/topic/instagram/", "social", True),
    ("https://www.socialmediatoday.com/topic/facebook/",  "social", True),
    ("https://www.socialmediatoday.com/topic/snapchat/",  "social", True),
    ("https://www.socialmediatoday.com/topic/pinterest/", "photo-text", True),
    ("https://www.socialmediatoday.com/topic/twitter/",   "photo-text", True),
]

TC_CATEGORIES = [
    ("https://techcrunch.com/category/media-entertainment/", "photo-text", True),
    ("https://techcrunch.com/category/apps/",               "social",     True),
    ("https://techcrunch.com/category/social/",             "social",     True),
]

def parse_relative_date(date_str):
    if not date_str: return False, ""
    ds = date_str.lower().strip()
    # 移除可能的 "updated" 字样
    ds = ds.replace("updated", "").strip()
    
    if any(x in ds for x in ["hour", "minute", "just now", "second"]):
        return True, date.today().strftime("%Y-%m-%d")
    if "1 day ago" in ds or "yesterday" in ds:
        return True, (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Try SMT format: March 24, 2026
    # 增加容错：处理不同的空格或特殊字符
    try:
        # 先尝试完整月份
        for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d %Y"]:
            try:
                dt = datetime.strptime(ds, fmt)
                iso = dt.strftime("%Y-%m-%d")
                today = date.today()
                # 范围扩大到 5 天内，确保能抓到最近的内容
                target_dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
                return iso in target_dates, iso
            except: continue
    except: pass
    return False, date_str

async def scrape_smt(browser):
    print("=== Scraping Social Media Today ===")
    all_items = []
    seen = set()
    for url, cat, priority in SMT_TOPICS:
        context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page = await context.new_page()
        apply_stealth(page)
        try:
            print(f"  Visiting {url}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)
            
            # 检查 Cloudflare
            if "blocked" in (await page.title()).lower():
                print(f"    [Blocked] Cloudflare detected on {url}")
                continue

            items = await page.query_selector_all("li.feed__item")
            count = 0
            for item in items:
                t_el = await item.query_selector("h3.feed__title a")
                if not t_el: continue
                title = (await t_el.inner_text()).strip()
                link = await t_el.get_attribute("href")
                if link and link.startswith("/"): link = "https://www.socialmediatoday.com" + link
                
                d_el = await item.query_selector("span.feed__date")
                d_str = await d_el.inner_text() if d_el else ""
                is_recent, p_date = parse_relative_date(d_str)
                
                if is_recent and link and link not in seen:
                    seen.add(link)
                    all_items.append({
                        "source": "Social Media Today",
                        "title": title, "summary": title, "url": link,
                        "date": p_date, "category": cat, "is_priority": priority
                    })
                    count += 1
            print(f"    Found {count} recent items")
        except Exception as e: print(f"    Error: {e}")
        finally: 
            await page.close()
            await context.close()
    return all_items

async def scrape_tc(browser):
    print("=== Scraping TechCrunch ===")
    all_items = []
    seen = set()
    for url, cat, priority in TC_CATEGORIES:
        context = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        page = await context.new_page()
        apply_stealth(page)
        try:
            print(f"  Visiting {url}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)
            
            posts = await page.query_selector_all(".post-block, article.post-block")
            count = 0
            for post in posts:
                t_el = await post.query_selector("h2.post-block__title a, h3.post-block__title a")
                if not t_el: continue
                title = (await t_el.inner_text()).strip()
                link = await t_el.get_attribute("href")
                
                time_el = await post.query_selector("time")
                dt_attr = await time_el.get_attribute("datetime") if time_el else ""
                
                article_date = ""
                is_recent = False
                if dt_attr:
                    article_date = dt_attr.split("T")[0]
                    today = date.today()
                    target_dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(5)]
                    is_recent = article_date in target_dates
                
                if is_recent and link and link not in seen:
                    seen.add(link)
                    all_items.append({
                        "source": "TechCrunch",
                        "title": title, "summary": title, "url": link,
                        "date": article_date, "category": cat, "is_priority": priority
                    })
                    count += 1
            print(f"    Found {count} recent items")
        except Exception as e: print(f"    Error: {e}")
        finally: 
            await page.close()
            await context.close()
    return all_items

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        smt_data = await scrape_smt(browser)
        tc_data = await scrape_tc(browser)
        await browser.close()
        
        with open("socialmediatoday_raw.json", "w", encoding="utf-8") as f:
            json.dump({"source": "Social Media Today", "items": smt_data}, f, ensure_ascii=False, indent=2)
        with open("techcrunch_raw.json", "w", encoding="utf-8") as f:
            json.dump({"source": "TechCrunch", "items": tc_data}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
