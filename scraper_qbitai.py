#!/usr/bin/env python3
"""
量子位 (QbitAI) 抓取脚本
- 从 qbitai.com 首页抓取过去 24 小时的文章
- 按相关性过滤（聚焦创作/AIGC/社交/图文方向）
- 输出格式与 tweets_raw.json 兼容，可直接接入日报流程
"""

import requests
import json
import re
import os
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

OUTPUT_FILE = "qbitai_raw.json"
STATE_FILE = "qbitai_state.json"

QBITAI_HOME = "https://www.qbitai.com/"
QBITAI_CATEGORY = "https://www.qbitai.com/category/%e8%b5%84%e8%ae%af"  # 资讯分类页

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

# 相关性关键词（聚焦创作/AIGC/社交/图文方向）
RELEVANT_KEYWORDS = [
    # AIGC 产品
    "sora", "vibes", "grok", "gemini", "veo", "midjourney",
    "runway", "可灵", "快手", "pixverse", "vidu", "minimax", "海螺",
    "阿里", "通义", "即梦", "suno", "udio", "mureka",
    "文生视频", "视频生成", "图像生成", "音乐生成",
    "dall-e", "stable diffusion", "flux",
    # 社交/创作平台
    "instagram", "facebook", "whatsapp", "meta", "snapchat",
    "tiktok", "抖音", "小红书", "youtube", "spotify",
    "telegram", "discord", "threads", "pinterest",
    "reels", "story", "短视频",
    # 模型/AI能力
    "大模型", "多模态", "ai生成", "aigc", "生成式ai",
    "文生图", "图生视频", "ai创作", "ai视频", "ai图像",
    "openai", "anthropic", "google", "meta ai",
    "chatgpt", "claude", "llm", "llama", "mistral",
    # 创作者/内容
    "创作者", "内容创作", "ugc", "投稿", "creator",
    # AI产品格局
    "ai产品", "agent", "copilot",
]

# AI头部公司重大进展 → 降低相关性门槛
HIGH_IMPORTANCE_COMPANIES = [
    "openai", "anthropic", "google deepmind", "google ai",
    "meta ai", "xai", "mistral",
]
HIGH_IMPORTANCE_SIGNALS = [
    "发布", "推出", "上线", "融资", "估值", "收购", "合并",
    "突破", "首个", "重大", "宣布", "战略",
    "launch", "release", "announce", "acquire", "raise",
]

# 明确不相关（即使重要也过滤）
IRRELEVANT_HARD_FILTER = [
    "具身智能", "自动驾驶", "机器人",
    "军事", "武器", "战争",
    "量子计算", "芯片制造",
    "房产", "外交", "政治",
    "汽车", "智能车", "电动车",
]


def load_state() -> datetime:
    """读取上次抓取时间"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return datetime.fromisoformat(data.get("last_run", "2000-01-01T00:00:00+00:00"))
        except Exception:
            pass
    return datetime.now(timezone.utc) - timedelta(hours=25)  # 默认抓25小时内


def save_state():
    """保存本次抓取时间"""
    with open(STATE_FILE, "w") as f:
        json.dump({"last_run": datetime.now(timezone.utc).isoformat()}, f)


def parse_relative_time(time_str: str) -> datetime | None:
    """
    解析量子位的相对时间格式：
    - "X小时前" → 减去X小时
    - "昨天 HH:MM" → 昨天
    - "前天 HH:MM" → 前天
    - "YYYY-MM-DD" → 固定日期
    """
    now = datetime.now(timezone.utc)
    china_tz = timezone(timedelta(hours=8))
    now_cn = datetime.now(china_tz)

    time_str = time_str.strip()

    # "X小时前"
    m = re.match(r"(\d+)小时前", time_str)
    if m:
        return now - timedelta(hours=int(m.group(1)))

    # "X分钟前"
    m = re.match(r"(\d+)分钟前", time_str)
    if m:
        return now - timedelta(minutes=int(m.group(1)))

    # "昨天 HH:MM"
    m = re.match(r"昨天\s*(\d{1,2}):(\d{2})", time_str)
    if m:
        yesterday = now_cn - timedelta(days=1)
        dt = yesterday.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0)
        return dt.astimezone(timezone.utc)

    # "前天 HH:MM"
    m = re.match(r"前天\s*(\d{1,2}):(\d{2})", time_str)
    if m:
        the_day = now_cn - timedelta(days=2)
        dt = the_day.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0)
        return dt.astimezone(timezone.utc)

    # "YYYY-MM-DD"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", time_str)
    if m:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      tzinfo=china_tz)
        return dt.astimezone(timezone.utc)

    return None


def is_relevant(title: str, summary: str = "") -> tuple[bool, str]:
    """
    判断文章是否相关
    返回 (is_relevant, reason)
    """
    combined = (title + " " + summary).lower()

    # 第一层：硬过滤
    for kw in IRRELEVANT_HARD_FILTER:
        if kw in combined:
            return False, f"硬过滤:{kw}"

    # 第二层：AI头部公司重大进展 → 降低门槛保留
    has_company = any(co in combined for co in HIGH_IMPORTANCE_COMPANIES)
    has_signal = any(sig in combined for sig in HIGH_IMPORTANCE_SIGNALS)
    if has_company and has_signal:
        return True, "高重要性"

    # 第三层：关键词匹配
    for kw in RELEVANT_KEYWORDS:
        if kw in combined:
            return True, f"关键词:{kw}"

    return False, "不相关"


def fetch_article_list() -> list[dict]:
    """
    抓取量子位首页文章列表
    返回 [{"title": ..., "url": ..., "time_str": ..., "article_id": ...}, ...]
    """
    seen_urls = set()
    articles = []

    for page_url in [QBITAI_HOME, QBITAI_CATEGORY]:
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.encoding = "utf-8"
            html = r.text
            soup = BeautifulSoup(html, "html.parser")

            # 先用正则从原始 HTML 中提取所有文章 URL
            all_article_urls = list(set(re.findall(
                r"https://www\.qbitai\.com/\d{4}/\d{2}/\d+\.html", html
            )))

            for href in all_article_urls:
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # 量子位同一URL有两个<a>：一个包图片，一个包标题
                # 找所有对应的 <a> 标签，取有文字内容的那个
                title = ""
                for a_tag in soup.find_all("a", href=href):
                    h = a_tag.find(["h3", "h4", "h2"])
                    if h:
                        title = h.get_text(strip=True)
                        break
                    t = a_tag.get_text(strip=True)
                    if len(t) > 5:
                        title = t
                        break

                if not title or len(title) < 5:
                    continue

                # 从 URL 中提取年月（量子位时间是 JS 渲染的）
                time_str = ""
                url_match = re.search(r"/(\d{4})/(\d{2})/", href)
                if url_match:
                    time_str = f"{url_match.group(1)}-{url_match.group(2)}-01"

                art_id_match = re.search(r"/(\d+)\.html", href)
                art_id = int(art_id_match.group(1)) if art_id_match else 0

                articles.append({
                    "title": title[:100],
                    "url": href,
                    "time_str": time_str,
                    "article_id": art_id,
                })

        except Exception as e:
            print(f"[量子位] 抓取 {page_url} 失败: {e}")

    # 按 URL 去重
    seen = set()
    unique = []
    for art in articles:
        if art["url"] not in seen:
            seen.add(art["url"])
            unique.append(art)

    print(f"[量子位] 找到 {len(unique)} 篇文章")
    return unique


def scrape() -> list[dict]:
    """主抓取逻辑"""
    now = datetime.now(timezone.utc)

    article_list = fetch_article_list()

    # 按文章ID降序排序（ID越大越新），只取前30篇（最新的）
    article_list.sort(key=lambda x: x.get("article_id", 0), reverse=True)
    article_list = article_list[:30]

    print(f"[量子位] 筛选最新 {len(article_list)} 篇文章（按文章ID排序）")

    items = []

    for art in article_list:
        title = art["title"]
        url = art["url"]
        time_str = art.get("time_str", "")

        # 量子位时间只有年月精度（YYYY-MM-01），不做精确过滤
        # 允许最近 3 天的文章，避免月初误删
        pub_time = parse_relative_time(time_str) if time_str else None
        if pub_time:
            if (now - pub_time).days > 3:
                continue

        # 相关性过滤
        relevant, reason = is_relevant(title)
        if not relevant:
            print(f"  [过滤] {title[:40]} ({reason})")
            continue

        print(f"  [保留] {title[:50]} ({reason})")

        items.append({
            "id": f"qbitai_{len(items)+1}",
            "author": "量子位",
            "title": title,
            "text": title,
            "summary": title,
            "created_at": (pub_time or now).isoformat(),
            "url": url,
            "source": "qbitai",
            "likes": 0,
            "retweets": 0,
        })

    return items


def main():
    print("=" * 55)
    print("量子位 抓取脚本")
    print("=" * 55)

    items = scrape()
    save_state()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": "qbitai",
            "total": len(items),
            "items": items,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[量子位] 共保留 {len(items)} 条相关文章 → {OUTPUT_FILE}")
    return items


if __name__ == "__main__":
    main()
