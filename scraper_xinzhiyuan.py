#!/usr/bin/env python3
"""
新智元 抓取脚本
- 从搜狐主页 (mp.sohu.com/profile?xpt=YWlfZXJhQHNvaHUuY29t) 抓取最新文章
- 新智元每篇文章都是独立文章（不像腾讯研究院是「AI速递」合集），直接取列表页
- 按相关性过滤（聚焦创作/AIGC/社交/图文方向）
- 输出格式与 tweets_raw.json 兼容，可直接接入日报流程
"""

import requests
import json
import re
import os
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

SOHU_PROFILE_URL = "https://mp.sohu.com/profile?xpt=YWlfZXJhQHNvaHUuY29t"
OUTPUT_FILE = "xinzhiyuan_raw.json"
STATE_FILE = "xinzhiyuan_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://mp.sohu.com/",
}

# 相关性关键词（与 scraper_tencent.py 保持一致）
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
    "ai产品", "agent", "copilot", "top100",
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

# 明确不相关（无论多重要都过滤）
IRRELEVANT_HARD_FILTER = [
    "具身智能", "自动驾驶", "机器人",
    "军事", "武器", "战争", "导弹",
    "量子计算", "芯片制造",
    "房产", "外交", "政治",
    "汽车", "电动车",
    "乒乓", "篮球", "足球", "体育",
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
    return datetime.now(timezone.utc) - timedelta(hours=25)


def save_state():
    """保存本次抓取时间"""
    with open(STATE_FILE, "w") as f:
        json.dump({"last_run": datetime.now(timezone.utc).isoformat()}, f)


def parse_sohu_time(time_str: str) -> datetime | None:
    """
    解析搜狐文章列表中的相对时间：
    - "X小时前"
    - "昨天HH:MM" / "昨天 HH:MM"
    - "前天HH:MM"
    - "YYYY-MM-DD"
    """
    now_utc = datetime.now(timezone.utc)
    china_tz = timezone(timedelta(hours=8))
    now_cn = datetime.now(china_tz)
    time_str = time_str.strip()

    m = re.match(r"(\d+)小时前", time_str)
    if m:
        return now_utc - timedelta(hours=int(m.group(1)))

    m = re.match(r"(\d+)分钟前", time_str)
    if m:
        return now_utc - timedelta(minutes=int(m.group(1)))

    m = re.match(r"昨天\s*(\d{1,2}):(\d{2})", time_str)
    if m:
        dt = (now_cn - timedelta(days=1)).replace(
            hour=int(m.group(1)), minute=int(m.group(2)), second=0)
        return dt.astimezone(timezone.utc)

    m = re.match(r"前天\s*(\d{1,2}):(\d{2})", time_str)
    if m:
        dt = (now_cn - timedelta(days=2)).replace(
            hour=int(m.group(1)), minute=int(m.group(2)), second=0)
        return dt.astimezone(timezone.utc)

    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", time_str)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        tzinfo=china_tz).astimezone(timezone.utc)

    return None


def is_relevant(title: str, summary: str = "") -> tuple[bool, str]:
    """判断文章是否相关"""
    combined = (title + " " + summary).lower()

    # 第一层：硬过滤
    for kw in IRRELEVANT_HARD_FILTER:
        if kw in combined:
            return False, f"硬过滤:{kw}"

    # 第二层：AI头部公司重大进展
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
    """从搜狐新智元主页抓取文章列表"""
    print(f"[新智元] 访问主页: {SOHU_PROFILE_URL}")
    articles = []

    try:
        r = requests.get(SOHU_PROFILE_URL, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        # 搜狐文章列表：每篇文章是一个 <a> 标签，href 是 sohu.com/a/XXXXXXXXX_XXXXXX
        seen_urls = set()
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            # 补全协议
            if href.startswith("//"):
                href = "https:" + href
            # 只取新智元文章 (473283 是新智元的账号ID，但也可能变化，用更宽松的匹配)
            if not re.match(r"https://www\.sohu\.com/a/\d+_\d+", href):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            # 获取标题和摘要
            title = ""
            summary = ""
            time_str = ""

            # 尝试从父容器获取更多信息
            parent = a_tag.find_parent(["div", "li", "article"])
            if parent:
                texts = [t.strip() for t in parent.stripped_strings if t.strip()]
                if texts:
                    # 第一段通常是标题
                    title = texts[0][:100] if texts else ""
                    # 第二段通常是摘要
                    summary = texts[1][:200] if len(texts) > 1 else ""

                    # 找时间：匹配相对时间模式
                    full_text = " ".join(texts)
                    m = re.search(
                        r"(\d+小时前|\d+分钟前|昨天\s*\d+:\d+|前天\s*\d+:\d+|\d{4}-\d{2}-\d{2})",
                        full_text
                    )
                    if m:
                        time_str = m.group(1)
            else:
                title = a_tag.get_text(strip=True)[:100]

            if not title or len(title) < 5:
                continue

            articles.append({
                "title": title,
                "summary": summary,
                "url": href,
                "time_str": time_str,
            })

    except Exception as e:
        print(f"[新智元] 主页抓取失败: {e}")

    print(f"[新智元] 找到 {len(articles)} 篇文章")
    return articles


def scrape() -> list[dict]:
    """主抓取逻辑"""
    last_run = load_state()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=25)
    since = max(last_run, cutoff)

    print(f"[新智元] 抓取时间范围: {since.strftime('%Y-%m-%d %H:%M')} UTC 之后")

    article_list = fetch_article_list()
    items = []

    for art in article_list:
        title = art["title"]
        summary = art.get("summary", "")
        url = art["url"]
        time_str = art.get("time_str", "")

        # 解析时间
        pub_time = parse_sohu_time(time_str) if time_str else None

        # 时间过滤
        if pub_time and pub_time < since:
            continue
        # 没有时间信息的保留（搜狐有时间渲染是 JS 动态的，可能解析不到）

        # 相关性过滤
        relevant, reason = is_relevant(title, summary)
        if not relevant:
            print(f"  [过滤] {title[:40]} ({reason})")
            continue

        print(f"  [保留] {title[:50]} ({reason})")

        items.append({
            "id": f"xinzhiyuan_{len(items)+1}",
            "author": "新智元",
            "title": title,
            "text": f"【{title}】{summary}" if summary else title,
            "summary": summary or title,
            "created_at": (pub_time or datetime.now(timezone.utc)).isoformat(),
            "url": url,
            "source": "xinzhiyuan",
            "likes": 0,
            "retweets": 0,
        })

    return items


def main():
    print("=" * 55)
    print("新智元 抓取脚本")
    print("=" * 55)

    items = scrape()
    save_state()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": "xinzhiyuan_sohu",
            "total": len(items),
            "items": items,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[新智元] 共保留 {len(items)} 条相关文章 → {OUTPUT_FILE}")
    return items


if __name__ == "__main__":
    main()
