#!/usr/bin/env python3
"""
腾讯研究院 AI速递 抓取脚本
- 从搜狐主页找到当天「AI速递」文章链接
- 抓取全文并解析每条动态
- 按相关性过滤（只保留与创作/AIGC/社交/图文方向相关的条目）
- 输出格式与 tweets_raw.json 兼容，可直接接入日报流程
"""

import requests
import json
import re
import os
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

SOHU_PROFILE_URL = "https://mp.sohu.com/profile?xpt=bGl1amluc29uZzIwMDBAMTI2LmNvbQ=="
AUTHOR_ID = "455313"  # 腾讯研究院搜狐账号ID
OUTPUT_FILE = "tencent_research_raw.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 相关性关键词（聚焦创作/AIGC/社交/图文方向）
RELEVANT_KEYWORDS = [
    # AIGC 产品
    "sora", "vibes", "grok", "gemini", "veo", "midjourney",
    "runway", "可灵", "快手", "pixverse", "vidu", "minimax", "海螺",
    "阿里", "通义", "即梦", "suno", "udio", "mureka",
    "文生视频", "视频生成", "图像生成", "音乐生成",
    "dall-e", "stable diffusion",
    # 社交/创作平台
    "instagram", "facebook", "whatsapp", "meta", "snapchat",
    "tiktok", "抖音", "小红书", "youtube", "spotify",
    "telegram", "discord", "threads",
    "reels", "story", "短视频",
    # 模型/AI能力
    "大模型", "多模态", "ai生成", "aigc", "生成式ai",
    "文生图", "图生视频", "ai创作", "ai视频", "ai图像",
    "openai", "anthropic", "google", "meta ai",
    # 创作者/内容
    "创作者", "内容创作", "ugc", "投稿", "creator",
    # AI产品格局
    "ai产品", "top100", "agent", "copilot", "办公", "workspace",
    "chatgpt", "claude", "gemini", "llm", "模型能力",
]

# AI头部公司 + 重大进展关键词：命中则降低相关性要求，只要不是明确不相关就保留
# 逻辑：这类动态即使不直接涉及创作/社交，也可能是重大行业事件
HIGH_IMPORTANCE_COMPANIES = [
    "openai", "anthropic", "google deepmind", "meta ai",
    "xai", "mistral", "cohere",
]
HIGH_IMPORTANCE_SIGNALS = [
    "发布", "推出", "上线", "融资", "估值", "收购", "合并",
    "突破", "最新", "首个", "重大", "宣布", "战略",
    "launch", "release", "announce", "acquire", "raise",
]

# 明确不相关（无论多重要都过滤）
IRRELEVANT_KEYWORDS = [
    "机器人", "具身智能", "自动驾驶",
    "军事", "武器", "战争", "导弹", "冲突", "打击",
    "量子计算", "芯片制造", "半导体",
    "房产", "外交", "政治", "科学家", "数学",
]

def find_today_article_url(target_date: str = None) -> tuple[str, str]:
    """
    从搜狐主页找到指定日期的「AI速递」文章链接
    target_date: YYYYMMDD 格式，默认今天
    返回 (url, title)
    """
    if not target_date:
        target_date = datetime.now().strftime("%Y%m%d")

    print(f"[搜狐] 正在查找 AI速递 {target_date} ...")

    try:
        r = requests.get(SOHU_PROFILE_URL, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        # 找所有文章链接
        links = soup.find_all("a", href=True)
        for link in links:
            href = link.get("href", "")
            # 补全协议头
            if href.startswith("//"):
                href = "https:" + href
            text = link.get_text(strip=True)
            # 匹配标题包含「AI速递 {date}」的链接
            if f"AI速递" in text and target_date in text and AUTHOR_ID in href:
                print(f"[搜狐] 找到：{text}")
                return href, text

        # 备用：直接在页面文本里匹配
        page_text = soup.get_text()
        pattern = rf"AI速递\s*{target_date}"
        if re.search(pattern, page_text):
            # 找对应的 sohu.com/a/ 链接
            all_hrefs = [a.get("href", "") for a in soup.find_all("a", href=True)]
            for href in all_hrefs:
                if f"sohu.com/a/" in href and AUTHOR_ID in href:
                    return href, f"腾讯研究院AI速递 {target_date}"

    except Exception as e:
        print(f"[搜狐] 主页抓取失败: {e}")

    return "", ""


def fetch_article_content(url: str) -> str:
    """抓取文章正文"""
    if url.startswith("//"):
        url = "https:" + url
    # 去掉 scm 等追踪参数，只保留核心 URL
    url = url.split("?")[0]
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        # 搜狐文章正文在 <article> 标签里
        content_div = (
            soup.find("article") or
            soup.find("div", class_="article") or
            soup.find("div", id="mp-editor") or
            soup.find("div", class_="content")
        )
        if content_div:
            return content_div.get_text(separator="\n", strip=True)

        return soup.get_text(separator="\n", strip=True)
    except Exception as e:
        print(f"[搜狐] 文章抓取失败: {e}")
        return ""


def parse_items(text: str, article_url: str, date_str: str) -> list[dict]:
    """
    解析文章中的每条动态
    腾讯研究院的格式是：
    一、标题\n1. 要点1\n2. 要点2\n3. 要点3\n链接
    """
    items = []
    
    # 按「一、二、三...」分割
    # 匹配中文数字序号：一、二、三...十
    CN_NUMS = "一二三四五六七八九十"
    pattern = rf"[{CN_NUMS}]、(.+?)(?=[{CN_NUMS}]、|\Z)"
    blocks = re.findall(pattern, text, re.DOTALL)

    if not blocks:
        # 备用：按换行分段
        blocks = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 20]

    for block in blocks:
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue

        title = lines[0].strip()
        full_text = " ".join(lines[1:])

        # 提取3个要点（格式：1. xxx；2. xxx；3. xxx）
        points = re.findall(r'[123][.、]\s*(.+?)(?=[123][.、]|$)', full_text)
        # 清理每个要点末尾的分号
        points = [p.rstrip("；;").strip() for p in points if len(p.strip()) > 5]

        # 找原文链接
        link = article_url
        for line in lines:
            if line.startswith("http") and "mp.weixin" in line or "sohu.com" in line:
                link = line.strip()
                break

        summary = " / ".join(points[:3]) if points else full_text[:150]

        # 相关性过滤
        combined = (title + " " + summary).lower()

        # 第一步：明确不相关的直接过滤（无论多重要）
        if any(kw in combined for kw in IRRELEVANT_KEYWORDS):
            print(f"  [过滤] {title[:40]}")
            continue

        # 第二步：AI头部公司 + 重大进展信号 → 降低相关性门槛，直接保留
        is_high_importance = (
            any(co in combined for co in HIGH_IMPORTANCE_COMPANIES) and
            any(sig in combined for sig in HIGH_IMPORTANCE_SIGNALS)
        )
        if is_high_importance:
            print(f"  [保留-重要] {title[:50]}")
        elif any(kw in combined for kw in RELEVANT_KEYWORDS):
            print(f"  [保留] {title[:50]}")
        else:
            print(f"  [过滤] {title[:40]}")
            continue
        items.append({
            "id": f"tencent_{date_str}_{len(items)+1}",
            "author": "腾讯研究院AI速递",
            "title": title,
            "text": f"【{title}】{summary}",
            "summary": summary,
            "created_at": datetime.now(timezone.utc).replace(
                hour=0, minute=1, second=0
            ).isoformat(),
            "url": link,
            "source": "tencent_research",
            "likes": 0,
            "retweets": 0,
        })

    return items


def scrape_today(target_date: str = None) -> list[dict]:
    """主入口：抓取指定日期的 AI速递"""
    if not target_date:
        target_date = datetime.now().strftime("%Y%m%d")

    url, title = find_today_article_url(target_date)
    if not url:
        print(f"[搜狐] 未找到 {target_date} 的 AI速递，可能尚未发布")
        return []

    print(f"[搜狐] 抓取文章内容: {url}")
    content = fetch_article_content(url)
    if not content:
        return []

    items = parse_items(content, url, target_date)
    print(f"[搜狐] 共保留 {len(items)} 条相关动态")
    return items


def main():
    print("=" * 55)
    print("腾讯研究院 AI速递 抓取脚本")
    print("=" * 55)

    # 抓今天
    today = datetime.now().strftime("%Y%m%d")
    items = scrape_today(today)

    # 如果今天的还没发（凌晨触发），也抓昨天的
    if not items:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        print(f"[搜狐] 尝试昨天 {yesterday}...")
        items = scrape_today(yesterday)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "source": "tencent_research_sohu",
            "total": len(items),
            "items": items,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n已保存 → {OUTPUT_FILE}")
    return items


if __name__ == "__main__":
    main()
