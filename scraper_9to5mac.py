#!/usr/bin/env python3
"""
9to5Mac Multi-Topic Scraper
目标：抓取多个 9to5Mac Guide 专题页面，获取最新文章
"""

import requests
import json
import re
from datetime import datetime, timezone, date, timedelta
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

# 专题 URL 配置：(url, 默认分类, 是否高优先级, slug)
TOPICS = [
    ("https://9to5mac.com/guides/chatgpt/",           "AIGC",     True,  "chatgpt"),
    ("https://9to5mac.com/guides/instagram/",         "social",   True,  "instagram"),
    ("https://9to5mac.com/guides/meta/",              "social",   True,  "meta"),
    ("https://9to5mac.com/guides/whatsapp/",          "social",   True,  "whatsapp"),
    ("https://9to5mac.com/guides/tiktok/",            "creation", True,  "tiktok"),
    ("https://9to5mac.com/guides/snapchat/",          "social",   True,  "snapchat"),
    ("https://9to5mac.com/guides/artificial-intelligence/", "AIGC", True, "artificial-intelligence"),
    ("https://9to5mac.com/guides/twitter/",           "photo-text", True, "twitter"),
]

def parse_article_date(date_str, link):
    """从文字描述或 URL 中解析文章日期，判断是否近期（今天/昨天）"""
    date_str_lower = date_str.lower() if date_str else ""

    # 相对时间描述
    if any(x in date_str_lower for x in ["hour", "minute", "just now"]):
        return True, date.today().strftime("%Y-%m-%d")

    if "1 day ago" in date_str_lower or "yesterday" in date_str_lower:
        return True, (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 从 URL 提取绝对日期 /YYYY/MM/DD/
    match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", link or "")
    if match:
        article_date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        today = date.today().strftime("%Y-%m-%d")
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        is_recent = article_date_str in [today, yesterday]
        return is_recent, article_date_str

    return False, date_str

def fetch_topic(url, default_category, is_priority):
    """抓取单个专题页面，返回近期文章列表"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[9to5Mac] 请求失败 {url}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    articles = soup.find_all("article", class_="article")

    results = []
    for art in articles:
        try:
            title_link = art.find("a", class_="article__title-link")
            if not title_link:
                continue

            title = title_link.get_text(strip=True)
            link = title_link.get("href", "")

            date_span = art.find("span", class_="meta__post-date")
            date_str = date_span.get_text(strip=True) if date_span else ""

            is_recent, parsed_date = parse_article_date(date_str, link)

            if is_recent:
                results.append({
                    "source": "9to5Mac",
                    "title": title,
                    "summary": title,
                    "url": link,
                    "date": parsed_date,
                    "category": default_category,
                    "is_priority": is_priority,
                    "topic_url": url
                })
        except Exception as e:
            print(f"[9to5Mac] 解析单条出错: {e}")
            continue

    return results

def main():
    print("=" * 55)
    print("9to5Mac Multi-Topic Scraper")
    print("=" * 55)

    all_items = []
    seen_urls = set()

    for url, category, is_priority, slug in TOPICS:
        label = "⭐高优" if is_priority else "普通"
        print(f"  [{label}] {url} ...", end=" ", flush=True)
        items = fetch_topic(url, category, is_priority)

        # 过滤并去重
        new_items = []
        for item in items:
            # 二次核验：标题或 URL 必须包含该专题 slug 关键词，排除页脚通用推荐
            # 例如 slug 是 'instagram'，标题里必须有 'instagram' 或 'ig'
            title_l = item["title"].lower()
            url_l = item["url"].lower()
            
            # 特殊处理：有些标题可能不带名字但属于该分类，但在 guide 页面中这通常意味着是推荐位
            # 我们采取保守策略，确保相关性
            keywords = [slug.lower()]
            if slug == "instagram": keywords.append("ig")
            if slug == "whatsapp": keywords.append("wa")
            if slug == "snapchat": keywords.append("snap")
            if slug == "chatgpt": keywords.append("ai")
            
            is_relevant = any(k in title_l or k in url_l for k in keywords)
            
            if is_relevant and item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                new_items.append(item)

        print(f"✅ {len(new_items)} 条近期文章")
        all_items.extend(new_items)

    print(f"\n✅ 9to5Mac 共抓取 {len(all_items)} 条（去重后）")
    for item in all_items[:5]:
        print(f"  - [{item['category']}] {item['title']} ({item['date']})")

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "9to5Mac",
        "items": all_items
    }

    with open("9to5mac_raw.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("Saved → 9to5mac_raw.json")
    return all_items

if __name__ == "__main__":
    main()
