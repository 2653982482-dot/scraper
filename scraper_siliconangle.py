#!/usr/bin/env python3
import requests
import json
from datetime import datetime, timezone, date, timedelta
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

URL = "https://siliconangle.com/author/mikewheatley/"

def parse_sa_date(date_str):
    date_str = date_str.lower()
    if any(x in date_str for x in ["hour", "minute", "just now", "second"]):
        return True, date.today().strftime("%Y-%m-%d")
    
    if "1 day ago" in date_str or "yesterday" in date_str:
        return True, (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if "days ago" in date_str:
        try:
            days = int(date_str.split()[0])
            if days <= 1:
                return True, (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        except:
            pass
            
    return False, date_str

def fetch_siliconangle():
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[SiliconANGLE] Request failed: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    # Articles are usually in divs with class "post-item" or similar
    # In the markdown: #### [Title](Link) ... BY MIKE WHEATLEY - 3 HOURS AGO ... Summary
    
    items = []
    # SiliconANGLE structure: usually h4 for titles in author page
    article_headers = soup.find_all("h4")
    
    for header in article_headers:
        try:
            a_tag = header.find("a")
            if not a_tag: continue
            
            title = a_tag.get_text(strip=True)
            link = a_tag.get("href", "")
            
            # Find metadata (author, date)
            # Usually in a div or span following the header
            meta_div = header.find_next("div", class_="post-meta") or header.find_next("span", class_="post-date")
            date_text = ""
            if meta_div:
                date_text = meta_div.get_text(strip=True)
            else:
                # Fallback: look for the text pattern
                sibling = header.find_next_sibling()
                if sibling:
                    date_text = sibling.get_text(strip=True)
            
            # Summary
            summary = ""
            summary_p = header.find_next("p")
            if summary_p:
                summary = summary_p.get_text(strip=True)
            
            is_recent, parsed_date = parse_sa_date(date_text)
            
            if is_recent:
                items.append({
                    "source": "SiliconANGLE",
                    "title": title,
                    "summary": summary if summary else title,
                    "url": link,
                    "date": parsed_date,
                    "is_priority": True  # High priority as per request
                })
        except Exception as e:
            print(f"[SiliconANGLE] Error parsing: {e}")
            continue
            
    return items

def main():
    print("SiliconANGLE (Mike Wheatley) Scraper starting...")
    items = fetch_siliconangle()
    print(f"✅ Found {len(items)} recent items.")
    
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "SiliconANGLE",
        "items": items
    }
    
    with open("siliconangle_raw.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("Saved → siliconangle_raw.json")

if __name__ == "__main__":
    main()
