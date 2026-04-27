#!/usr/bin/env python3
import requests
import json
from datetime import datetime, timezone, date, timedelta
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

URL = "https://www.aizws.net/news/list?page=1"

def fetch_aizws():
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[AIZWS] Request failed: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    # Structure: h3 with links, summary text, date 2026-03-25
    
    items = []
    # Typical structure on aizws list: news-item or just finding h3
    articles = soup.find_all("div", class_="news-item") or soup.find_all("div", class_=lambda x: x and "item" in x)
    
    if not articles:
        # Fallback to H3 search
        articles = soup.find_all("h3")

    today_str = date.today().strftime("%Y-%m-%d")
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    for art in articles:
        try:
            # If art is H3, then we look for link in it
            if art.name == "h3":
                title_tag = art
            else:
                title_tag = art.find("h3")
            
            if not title_tag: continue
            a_tag = title_tag.find("a")
            if not a_tag: continue
            
            title = a_tag.get_text(strip=True)
            link = a_tag.get("href", "")
            if link.startswith("/"):
                link = "https://www.aizws.net" + link
            
            # Summary & Date
            summary = ""
            date_text = ""
            
            parent = title_tag.parent
            # Look for summary text
            summary_tag = parent.find("div", class_="summary") or parent.find("p")
            if summary_tag:
                summary = summary_tag.get_text(strip=True)
            
            # Look for date
            date_tag = parent.find("span", class_="time") or parent.find(string=lambda x: x and ("202" in x))
            if date_tag:
                date_text = date_tag.strip()
            
            # Simple date match
            is_recent = today_str in date_text or yesterday_str in date_text
            
            # If date_text is not found properly, check nearby siblings
            if not is_recent:
                # Based on markdown: date is below the summary
                next_text = title_tag.find_next(string=lambda x: x and ("202" in x))
                if next_text:
                    is_recent = today_str in next_text or yesterday_str in next_text
                    date_text = next_text.strip()

            if is_recent:
                items.append({
                    "source": "AI中文网",
                    "title": title,
                    "summary": summary if summary else title,
                    "url": link,
                    "date": date_text[:10]
                })
        except Exception as e:
            print(f"[AIZWS] Error parsing: {e}")
            continue
            
    return items

def main():
    print("AIZWS Scraper starting...")
    items = fetch_aizws()
    print(f"✅ Found {len(items)} recent items.")
    
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "AI中文网",
        "items": items
    }
    
    with open("aizws_raw.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("Saved → aizws_raw.json")

if __name__ == "__main__":
    main()
