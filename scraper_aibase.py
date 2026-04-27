#!/usr/bin/env python3
"""
AIBase AI日报 Scraper
目标：news.aibase.com/zh/daily — 每日 AI 日报聚合
策略：抓取列表页找今日（或最新一篇）文章，解析正文条目
"""

import requests
import re
import json
from datetime import datetime, timezone, date
from bs4 import BeautifulSoup

BASE_URL = "https://news.aibase.com"
LIST_URL = "https://news.aibase.com/zh/daily"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://news.aibase.com/",
}


def fetch_latest_daily_url():
    """从列表页获取最新（今日或昨日）日报 URL"""
    try:
        r = requests.get(LIST_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[AIBase] 列表页请求失败: {e}")
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.find_all("a", href=lambda h: h and "/daily/" in h and h != "/zh/daily")

    if not links:
        print("[AIBase] 未找到日报链接")
        return None, None

    # 第一个链接即最新一篇
    href = links[0].get("href")
    title = links[0].get_text(strip=True)[:60]
    full_url = BASE_URL + href if href.startswith("/") else href
    print(f"[AIBase] 最新日报: {title} → {full_url}")
    return full_url, title


def parse_daily_article(url):
    """解析日报正文，提取各条目"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[AIBase] 正文请求失败: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    main = soup.find("main") or soup.find("body")
    if not main:
        print("[AIBase] 未找到正文容器")
        return []

    text = main.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # 解析结构：日报条目通常以 "N、标题" 或 "N. 标题" 开头
    items = []
    current_title = None
    current_body = []
    item_pattern = re.compile(r"^(\d+)[、.．。]\s*(.+)$")

    # 找到正文开始位置（跳过导航/头图文字）
    start_idx = 0
    for i, line in enumerate(lines):
        if re.match(r"^1[、.．。]", line):
            start_idx = i
            break

    for line in lines[start_idx:]:
        m = item_pattern.match(line)
        if m:
            # 保存上一条
            if current_title:
                body_text = "\n".join(current_body).strip()
                # 过滤掉纯导航/AiBase提要行
                body_clean = _clean_body(body_text)
                items.append({
                    "title": current_title,
                    "body": body_clean,
                    "source_url": url,
                })
            current_title = m.group(2).strip()
            current_body = []
        else:
            # 跳过 AiBase 标记行和提要头
            if line.startswith("【AiBase提要"):
                continue
            if re.match(r"^[🔄🧠🌐🚀🎭🔒✨📊⚠️🗣️🔊📅🔍💡]+", line):
                # emoji bullet，加入 body
                current_body.append(line)
            elif current_title:
                current_body.append(line)

    # 收尾最后一条
    if current_title and current_body:
        body_clean = _clean_body("\n".join(current_body).strip())
        items.append({
            "title": current_title,
            "body": body_clean,
            "source_url": url,
        })

    print(f"[AIBase] 解析到 {len(items)} 条条目")
    return items


def _clean_body(text):
    """清理正文，移除无用行"""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 跳过纯链接行（详情链接、Huggingface 等）
        if line.startswith("详情链接") or line.startswith("http"):
            continue
        # 跳过 AiBase 提要标题行
        if "AiBase提要" in line:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def format_for_report(items, article_url):
    """将条目格式化为日报所需结构（类似其他 scraper 的输出）"""
    results = []
    for item in items:
        results.append({
            "source": "AIBase日报",
            "title": item["title"],
            "summary": item["body"][:200] if item["body"] else item["title"],
            "url": article_url,
            "category": _classify(item["title"] + " " + item["body"]),
        })
    return results


def _classify(text):
    """简单分类，复用日报分类规则"""
    text_lower = text.lower()
    # AIGC 优先
    aigc_kw = [
        "ai", "模型", "大模型", "生成", "gpt", "llm", "语言模型",
        "文生图", "文生视频", "图像生成", "视频生成", "stable diffusion",
        "midjourney", "sora", "runway", "可灵", "kling", "海螺",
        "suno", "udio", "tts", "语音合成", "voice", "agent", "智能体",
        "embedding", "多模态", "推理", "inference",
    ]
    social_kw = [
        "微信", "wechat", "instagram", "facebook", "whatsapp", "tiktok",
        "snapchat", "twitter", "telegram", "discord", "threads",
        "社交", "dm", "评论", "点赞", "分享", "好友",
    ]
    creation_kw = [
        "视频创作", "剪辑", "滤镜", "特效", "模板", "创作工具",
        "reel", "story", "短视频", "投稿", "draft",
    ]

    if any(kw in text_lower for kw in aigc_kw):
        return "AIGC"
    if any(kw in text_lower for kw in social_kw):
        return "social"
    if any(kw in text_lower for kw in creation_kw):
        return "creation"
    return "other"


def main():
    print("=" * 50)
    print("AIBase 日报 Scraper")
    print("=" * 50)

    url, title = fetch_latest_daily_url()
    if not url:
        print("[AIBase] 无法获取日报，退出")
        return []

    items = parse_daily_article(url)
    if not items:
        print("[AIBase] 无条目解析，退出")
        return []

    formatted = format_for_report(items, url)

    # 保存
    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source": "AIBase AI日报",
        "article_url": url,
        "article_title": title,
        "total": len(formatted),
        "items": formatted,
    }
    with open("aibase_raw.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ 共 {len(formatted)} 条，已保存 → aibase_raw.json")

    # 打印预览
    print("\n--- 前5条预览 ---")
    for item in formatted[:5]:
        print(f"[{item['category']}] {item['title']}")
        print(f"  {item['summary'][:80]}...")
        print()

    return formatted


if __name__ == "__main__":
    main()
