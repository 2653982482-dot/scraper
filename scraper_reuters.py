#!/usr/bin/env python3
import requests
import json
from datetime import datetime, timezone, date, timedelta
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

URL = "https://www.reuters.com/technology/"

def parse_date(date_str):
    date_str = date_str.lower()
    if any(x in date_str for x in ["hour", "minute", "just now", "second"]):
        return True, date.today().strftime("%Y-%m-%d")
    
    # Check for specific dates
    today_str = date.today().strftime("%B %d, %Y")
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%B %d, %Y")
    
    if today_str.lower() in date_str:
        return True, date.today().strftime("%Y-%m-%d")
    if yesterday_str.lower() in date_str:
        return True, (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    return False, date_str

def fetch_reuters():
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[Reuters] Request failed: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    # Articles are often in data-testid="StoryCard" or similar
    # Based on the markdown structure:
    # 1. Look for H3 with links
    # 2. Look for the date/time info nearby
    
    items = []
    # Reuters uses a specific structure for cards
    story_cards = soup.find_all("li", class_=lambda x: x and "story-card" in x)
    if not story_cards:
        # Fallback to searching for all H3s
        story_cards = soup.find_all("div", {"data-testid": "StoryCard"})

    for card in story_cards:
        try:
            title_tag = card.find("h3")
            if not title_tag: continue
            a_tag = title_tag.find("a")
            if not a_tag: continue
            
            title = a_tag.get_text(strip=True)
            link = "https://www.reuters.com" + a_tag.get("href", "") if a_tag.get("href", "").startswith("/") else a_tag.get("href", "")
            
            # Summary - usually in a paragraph or span
            summary = ""
            summary_tag = card.find("p") or card.find("span", {"data-testid": "Body"})
            if summary_tag:
                summary = summary_tag.get_text(strip=True)
            
            # Date/Time
            time_tag = card.find("time") or card.find("span", {"data-testid": "Label"})
            date_text = time_tag.get_text(strip=True) if time_tag else ""
            
            is_recent, parsed_date = parse_date(date_text)
            
            if is_recent:
                items.append({
                    "source": "Reuters Technology",
                    "title": title,
                    "summary": summary if summary else title,
                    "url": link,
                    "date": parsed_date
                })
        except Exception as e:
            print(f"[Reuters] Error parsing card: {e}")
            continue
            
    return items

def main():
    print("Reuters Technology Scraper starting...")
    items = fetch_reuters()
    print(f"✅ Found {len(items)} recent items.")
    
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "Reuters Technology",
        "items": items
    }
    
    with open("reuters_raw.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("Saved → reuters_raw.json")

if __name__ == "__main__":
    main()
