# -*- coding: utf-8 -*-
"""
若本地存在 scraper.py 的 RELEVANT_KEYWORDS 则优先读取，否则使用内置回退。

功能：
- 抓取 Reddit 若干 subreddit 的 hot 帖子 JSON 接口
- 过滤条件：过去 24 小时、关键词匹配、score >= 100
- 增量：使用 reddit_state.json 记录上次抓取时间，仅抓新内容
- 输出：reddit_raw.json，数组元素字段：source、title、text、url、score、created_utc
- 容错：单个 subreddit 失败不影响其他源，记录 warning 并继续
- 日志：控制台打印简要过程；warning 写入 warnings.log；统计与预览写入 test_output.txt
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib import error, request


LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
STATE_FILE = "reddit_state.json"
OUTPUT_FILE = "reddit_raw.json"
WARNINGS_FILE = "warnings.log"
TEST_OUTPUT_FILE = "test_output.txt"

SUBREDDITS = [
    "artificial",
    "StableDiffusion",
    "MachineLearning",
    "technology",
    "singularity",
]


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("scraper_reddit")
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
    except Exception as e:  # ModuleNotFoundError 等
        logger.warning("无法从 scraper.py 读取 RELEVANT_KEYWORDS，将使用内置回退：%s", e)

    return [k.lower() for k in fallback_keywords]


def load_last_run(logger: logging.Logger) -> Optional[float]:
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("last_run")
        if isinstance(ts, (int, float, str)):
            return float(ts)
        logger.warning("状态文件 %s 中 last_run 字段格式异常，将忽略增量信息", STATE_FILE)
    except Exception as e:
        logger.warning("读取状态文件 %s 失败，将忽略增量信息：%s", STATE_FILE, e)
    return None


def save_last_run(logger: logging.Logger, ts: float) -> None:
    try:
        payload = {"last_run": ts}
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        logger.info("已更新状态文件 %s，last_run=%.0f", STATE_FILE, ts)
    except Exception as e:
        logger.warning("写入状态文件 %s 失败：%s", STATE_FILE, e)


def matches_keywords(text: str, keywords: List[str]) -> bool:
    text_l = (text or "").lower()
    for kw in keywords:
        if kw and kw in text_l:
            return True
    return False


def fetch_subreddit(
    subreddit: str,
    keywords: List[str],
    since_ts: float,
    window_start_ts: float,
    logger: logging.Logger,
) -> List[Dict]:
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
    headers = {
        "User-Agent": "AimeDailyIntelBot/0.1 (+https://bytedance.com)"
    }
    req = request.Request(url, headers=headers)

    try:
        with request.urlopen(req, timeout=20) as resp:
            if resp.status != 200:
                logger.warning("请求 subreddit %s 失败，HTTP %s", subreddit, resp.status)
                return []
            raw = resp.read().decode("utf-8", errors="replace")
    except error.URLError as e:
        logger.warning("请求 subreddit %s 发生网络错误：%s", subreddit, e)
        return []
    except Exception as e:
        logger.warning("请求 subreddit %s 发生未知错误：%s", subreddit, e)
        return []

    try:
        data = json.loads(raw)
    except Exception as e:
        logger.warning("解析 subreddit %s 的 JSON 失败：%s", subreddit, e)
        return []

    children = (
        data.get("data", {}).get("children", [])
        if isinstance(data, dict)
        else []
    )

    results: List[Dict] = []
    for item in children:
        post = item.get("data") if isinstance(item, dict) else None
        if not isinstance(post, dict):
            continue

        created_utc = post.get("created_utc")
        try:
            created_ts = float(created_utc)
        except (TypeError, ValueError):
            continue

        # 24 小时窗口过滤
        if created_ts < window_start_ts:
            continue

        # 增量过滤
        if created_ts <= since_ts:
            continue

        score = post.get("score", 0)
        try:
            score_val = int(score)
        except (TypeError, ValueError):
            score_val = 0

        if score_val < 100:
            continue

        title = post.get("title") or ""
        selftext = post.get("selftext") or ""

        full_text = f"{title}\n{selftext}"
        if not matches_keywords(full_text, keywords):
            continue

        permalink = post.get("permalink") or ""
        if permalink.startswith("/"):
            full_url = "https://www.reddit.com" + permalink
        elif permalink:
            full_url = permalink
        else:
            full_url = post.get("url") or ""

        entry = {
            "source": f"r/{subreddit}",
            "title": title,
            "text": selftext[:500],
            "url": full_url,
            "score": score_val,
            "created_utc": created_ts,
        }
        results.append(entry)

    logger.info(
        "subreddit %s 过滤后得到 %d 条结果", subreddit, len(results)
    )
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
    lines.append(f"=== scraper_reddit.py run at {now_iso} (UTC) ===")
    lines.append("Reddit 各 subreddit 抓取条数：")
    if counts:
        for src in sorted(counts.keys()):
            lines.append(f"  {src}: {counts[src]}")
    else:
        lines.append("  无数据（可能网络异常或暂无符合条件的帖子）")

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
    logger.info("开始运行 scraper_reddit.py")

    keywords = load_keywords(logger)
    logger.info("关键词数量：%d", len(keywords))

    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(hours=24)
    window_start_ts = window_start.timestamp()

    last_run_ts = load_last_run(logger)
    if last_run_ts is None:
        since_ts = window_start_ts
        logger.info(
            "首次运行或状态不可用，将使用过去 24 小时作为增量起点"
        )
    else:
        since_ts = max(last_run_ts, window_start_ts)
        logger.info(
            "读取到上次运行时间：%.0f（增量起点=%.0f）",
            last_run_ts,
            since_ts,
        )

    all_records: List[Dict] = []

    for sub in SUBREDDITS:
        sub_name = sub
        try:
            records = fetch_subreddit(
                subreddit=sub_name,
                keywords=keywords,
                since_ts=since_ts,
                window_start_ts=window_start_ts,
                logger=logger,
            )
            all_records.extend(records)
        except Exception as e:
            logger.warning("处理 subreddit %s 过程中出现未捕获异常：%s", sub_name, e)

        # 简单节流，避免过快请求
        time.sleep(1)

    write_output(logger, all_records)
    log_test_summary(logger, all_records)
    save_last_run(logger, now_utc.timestamp())

    logger.info("scraper_reddit.py 运行结束，总记录数=%d", len(all_records))


if __name__ == "__main__":
    main()
