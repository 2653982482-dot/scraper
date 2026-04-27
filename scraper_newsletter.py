# -*- coding: utf-8 -*-
"""
若本地存在 scraper.py 的 RELEVANT_KEYWORDS 则优先读取，否则使用内置回退。

功能：
- 通过 RSS 抓取若干 AI 相关 Newsletter
- 过滤条件：过去 24 小时、关键词匹配
- 输出：newsletter_raw.json，数组元素字段：source、title、summary、url、published(ISO UTC)
- 容错：单个 RSS 源失败不影响其他源，记录 warning 并继续
- 日志：控制台打印简要过程；warning 写入 warnings.log；统计与预览写入 test_output.txt
"""

import calendar
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
OUTPUT_FILE = "newsletter_raw.json"
WARNINGS_FILE = "warnings.log"
TEST_OUTPUT_FILE = "test_output.txt"

NEWSLETTER_SOURCES = [
    {"name": "The Rundown AI", "url": "https://www.therundown.ai/rss"},
    {"name": "Import AI (Jack Clark)", "url": "https://importai.substack.com/feed"},
    {"name": "AI Breakfast", "url": "https://aibreakfast.beehiiv.com/feed"},
    {"name": "The Batch (deeplearning.ai)", "url": "https://www.deeplearning.ai/the-batch/rss.xml"},
    {"name": "Ben's Bites", "url": "https://bensbites.beehiiv.com/feed"},
]


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("scraper_newsletter")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(WARNINGS_FILE, encoding="utf-8")
    file_handler.setLevel(logging.WARNING)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(file_handler)

    return logger


def load_keywords(logger: logging.Logger) -> List[str]:
    """加载关键词：优先从 scraper.py 导入 RELEVANT_KEYWORDS，否则使用内置回退。"""
    fallback_keywords = [
        # AIGC
        "sora",
        "vibes",
        "gemini",
        "gpt",
        "claude",
        "midjourney",
        "stable diffusion",
        "runway",
        "kling",
        "pika",
        "suno",
        "udio",
        "veo",
        "wan",
        "vidu",
        "minimax",
        "haiku",
        "grok",
        "flux",
        "imagen",
        "dall-e",
        "firefly",
        "meta ai",
        "llama",
        "mistral",
        "anthropic",
        "openai",
        "ai model",
        "ai video",
        "ai music",
        "ai image",
        "text to video",
        "text to image",
        # 社交/创作
        "instagram",
        "reels",
        "tiktok",
        "snapchat",
        "facebook",
        "whatsapp",
        "youtube shorts",
        "creator",
        "short video",
        "content creation",
        # 平台
        "reddit",
        "x.com",
        "twitter",
        "pinterest",
        "threads",
    ]

    try:
        import scraper  # type: ignore

        if hasattr(scraper, "RELEVANT_KEYWORDS"):
            raw_kw = getattr(scraper, "RELEVANT_KEYWORDS")
            if isinstance(raw_kw, (list, tuple)):
                logger.info("从 scraper.py 读取 RELEVANT_KEYWORDS 成功，共 %d 个", len(raw_kw))
                return [str(k).lower() for k in raw_kw]
            else:
                logger.warning("scraper.RELEVANT_KEYWORDS 类型异常，使用内置关键词回退")
        else:
            logger.warning("scraper.py 中未找到 RELEVANT_KEYWORDS，使用内置关键词回退")
    except Exception as e:
        logger.warning("无法从 scraper.py 读取 RELEVANT_KEYWORDS，将使用内置回退：%s", e)

    return [k.lower() for k in fallback_keywords]


def ensure_feedparser(logger: logging.Logger):
    try:
        import feedparser  # type: ignore  # noqa: F401
        return
    except ImportError:
        logger.info("未检测到 feedparser，尝试通过 pip 安装...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "feedparser"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            import feedparser  # type: ignore  # noqa: F401
            logger.info("feedparser 安装成功")
        except Exception as e:  # 安装失败
            logger.warning("安装 feedparser 失败，Newsletter 抓取将被跳过：%s", e)
            raise


def matches_keywords(text: str, keywords: List[str]) -> bool:
    text_l = (text or "").lower()
    for kw in keywords:
        if kw and kw in text_l:
            return True
    return False


def parse_time_to_utc(entry, logger: logging.Logger) -> Optional[datetime]:
    """从 feed 条目解析时间，并统一转换为 UTC。"""
    t = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if not t:
        return None
    try:
        ts = calendar.timegm(t)  # struct_time 视为 UTC
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception as e:
        logger.warning("解析 RSS 时间失败：%s", e)
        return None


def fetch_newsletter(
    name: str,
    url: str,
    keywords: List[str],
    window_start: datetime,
    logger: logging.Logger,
) -> List[Dict]:
    import feedparser  # type: ignore

    logger.info("抓取 Newsletter：%s", name)

    try:
        feed = feedparser.parse(url)
    except Exception as e:
        logger.warning("请求 Newsletter %s 失败：%s", name, e)
        return []

    status = getattr(feed, "status", None)
    if status is not None and status != 200:
        logger.warning("Newsletter %s HTTP 状态异常：%s，跳过", name, status)
        return []

    entries = getattr(feed, "entries", []) or []

    results: List[Dict] = []
    for entry in entries:
        published_dt = parse_time_to_utc(entry, logger)
        if not published_dt:
            continue
        if published_dt < window_start:
            continue

        title = getattr(entry, "title", "") or ""
        summary = getattr(entry, "summary", "") or ""
        link = getattr(entry, "link", "") or ""

        full_text = f"{title}\n{summary}"
        if not matches_keywords(full_text, keywords):
            continue

        results.append(
            {
                "source": name,
                "title": title,
                "summary": summary,
                "url": link,
                "published": published_dt.isoformat(),
            }
        )

    logger.info("Newsletter %s 过滤后得到 %d 条结果", name, len(results))
    return results


def write_output(logger: logging.Logger, records: List[Dict]) -> None:
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    records,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        logger.info("已写入 %s，记录数=%d", OUTPUT_FILE, len(records))
    except Exception as e:
        logger.warning("写入输出文件 %s 失败：%s", OUTPUT_FILE, e)


def log_test_summary(logger: logging.Logger, records: List[Dict]) -> None:
    counts: Dict[str, int] = {}
    for r in records:
        src = r.get("source", "unknown")
        counts[src] = counts.get(src, 0) + 1

    now_iso = datetime.now(timezone.utc).isoformat()
    lines: List[str] = []
    lines.append(f"=== scraper_newsletter.py run at {now_iso} (UTC) ===")
    lines.append("可用的 RSS 源列表及抓取条数：")
    if counts:
        for src in sorted(counts.keys()):
            lines.append(f"  {src}: {counts[src]}")
    else:
        lines.append("  无数据（可能网络异常、feed 不可用或暂无符合条件的内容）")

    if records:
        lines.append("前几条预览（最多 5 条）：")
        for r in records[:5]:
            title = (r.get("title") or "").replace("\n", " ")
            url = r.get("url") or ""
            src = r.get("source") or ""
            lines.append(f"- [{src}] {title} | {url}")
    lines.append("")

    text = "\n".join(lines)

    try:
        with open(TEST_OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception as e:
        logger.warning("写入测试日志 %s 失败：%s", TEST_OUTPUT_FILE, e)

    # 也打印到控制台，方便查看
    print(text)


def main() -> None:
    logger = setup_logger()
    logger.info("开始运行 scraper_newsletter.py")

    keywords = load_keywords(logger)
    logger.info("关键词数量：%d", len(keywords))

    try:
        ensure_feedparser(logger)
    except Exception:
        # ensure_feedparser 已记录 warning
        # 记录一条测试日志，说明本次 Newsletter 抓取失败
        now_iso = datetime.now(timezone.utc).isoformat()
        msg = (
            f"=== scraper_newsletter.py run at {now_iso} (UTC) ===\n"
            "Newsletter 抓取失败：feedparser 不可用，详见 warnings.log\n\n"
        )
        try:
            with open(TEST_OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(msg)
        except Exception:
            pass
        logger.info("scraper_newsletter.py 因 feedparser 不可用提前结束")
        return

    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(hours=24)

    all_records: List[Dict] = []

    for src in NEWSLETTER_SOURCES:
        name = src["name"]
        url = src["url"]
        try:
            records = fetch_newsletter(
                name=name,
                url=url,
                keywords=keywords,
                window_start=window_start,
                logger=logger,
            )
            all_records.extend(records)
        except Exception as e:
            logger.warning("处理 Newsletter %s 过程中出现未捕获异常：%s", name, e)

    write_output(logger, all_records)
    log_test_summary(logger, all_records)

    logger.info("scraper_newsletter.py 运行结束，总记录数=%d", len(all_records))


if __name__ == "__main__":
    main()
