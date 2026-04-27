#!/usr/bin/env python3
"""
Social Media Today Topic Scraper
目标：抓取 Social Media Today 指定 Topic 页面
"""

import requests
import json
import re
from datetime import datetime, timezone, date, timedelta
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# (url, 默认分类, 是否高优先级)
TOPICS = [
    ("https://www.socialmediatoday.com/topic/instagram/", "social", True),
    ("https://www.socialmediatoday.com/topic/facebook/",  "social", True),
    ("https://www.socialmediatoday.com/topic/snapchat/",  "social", True),
    ("https://www.socialmediatoday.com/topic/pinterest/", "photo-text", True),
    ("https://www.socialmediatoday.com/topic/twitter/",   "photo-text", True),
]

def parse_smt_date(date_str):
    """从文字描述中解析日期"""
    date_str_lower = date_str.lower() if date_str else ""
    
    # Social Media Today 通常显示 "March 24, 2026" 或 "2 hours ago"
    if any(x in date_str_lower for x in ["hour", "minute", "just now"]):
        return True, date.today().strftime("%Y-%m-%d")
    
    if "1 day ago" in date_str_lower or "yesterday" in date_str_lower:
        return True, (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 尝试解析 "March 24, 2026"
    try:
        # 去掉多余的空格
        dt = datetime.strptime(date_str_lower.strip(), "%b. %d, %Y")
        article_date_str = dt.strftime("%Y-%m-%d")
        today = date.today().strftime("%Y-%m-%d")
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        return article_date_str in [today, yesterday], article_date_str
    except:
        pass
        
    return False, date_str

def fetch_topic(url, default_category, is_priority):
    """抓取单 Topic 页面"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[SocialMediaToday] 请求失败 {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    # 文章列表通常在 feed__item
    items = soup.find_all("li", class_="feed__item")
    
    results = []
    for item in items:
        try:
            h3 = item.find("h3", class_="feed__title")
            if not h3: continue
            
            a_tag = h3.find("a")
            if not a_tag: continue
            
            title = a_tag.get_text(strip=True)
            link = "https://www.socialmediatoday.com" + a_tag.get("href", "")
            
            # Summary
            summary_p = item.find("p", class_="feed__description")
            summary = summary_p.get_text(strip=True) if summary_p else title
            
            # Date
            date_span = item.find("span", class_="feed__date")
            date_str = date_span.get_text(strip=True) if date_span else ""
            
            is_recent, parsed_date = parse_smt_date(date_str)
            
            if is_recent:
                results.append({
                    "source": "Social Media Today",
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "date": parsed_date,
                    "category": default_category,
                    "is_priority": is_priority
                })
        except Exception as e:
            print(f"[SocialMediaToday] 解析单条出错: {e}")
            continue
            
    return results

def main():
    print("=" * 55)
    print("Social Media Today Topic Scraper")
    print("=" * 55)
    
    all_items = []
    seen_urls = set()
    
    for url, category, is_priority in TOPICS:
        print(f"  抓取 {url} ...", end=" ", flush=True)
        items = fetch_topic(url, category, is_priority)
        
        new_items = []
        for item in items:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                new_items.append(item)
        
        print(f"✅ {len(new_items)} 条近期文章")
        all_items.extend(new_items)
        
    print(f"\n✅ Social Media Today 共抓取 {len(all_items)} 条（去重后）")
    
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "Social Media Today",
        "items": all_items
    }
    
    with open("socialmediatoday_raw.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    print("Saved → socialmediatoday_raw.json")
    return all_items

if __name__ == "__main__":
    main()
