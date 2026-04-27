#!/usr/bin/env python3
"""
X (Twitter) Tweet Scraper - GraphQL API + Cookie Auth
Optimizations:
  1. Account tiering (must-read vs filtered)
  2. Relevance keyword filter at scrape time
  3. Incremental update (timestamp-based, no re-processing old content)
"""

import requests
import json
import os
import time
from datetime import datetime, timezone, timedelta

# ============ COOKIES ============
# NOTE: For safety, real cookie values are NOT written by the assistant.
# Replace the placeholders with your own cookie values before running.
COOKIES = {
    "auth_token": "REPLACE_ME",
    "ct0": "REPLACE_ME",
    # Optional:
    # "twid": "u%3D123...",
}
CT0 = COOKIES["ct0"]

BEARER = "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

HEADERS = {
    "authorization": BEARER,
    "x-csrf-token": CT0,
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "x-twitter-active-user": "yes",
    "x-twitter-auth-type": "OAuth2Session",
    "content-type": "application/json",
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://x.com/",
}

# ============ OPT 1: ACCOUNT TIERING ============
# must_read: every tweet is processed regardless of engagement
# filtered: only keep tweets with likes >= MIN_LIKES_FILTERED or RT >= MIN_RT_FILTERED
ACCOUNTS_MUST_READ = [
    # === Priority 1 (最高): Instagram 产品更新 — 全量收录，无互动门槛 ===
    "chetaslua",        # AI/大模型动态追踪
    "venturetwins",     # Happy Horse 1.0 等AIGC模型追踪
    "ArtificialAnlys",  # AI/大模型领域深度评测与数据分析
    "instagram",        # Instagram官号
    "mosseri",          # Instagram CEO
    "alex193a",         # Instagram功能爆料
    "oncescuradu",      # Instagram功能爆料
    "liahaberman",      # Meta产品（IG相关）

    # === Priority 2: Meta 家族其他产品 — 放宽门槛，真实功能更新均收录 ===
    "WABetaInfo",       # WhatsApp功能爆料，几乎每条都有价值
    "wcathcart",        # WhatsApp CEO
    "messenger",        # Messenger官号
    "AIatMeta",         # Meta AI官号
    "PixVerse_",        # Vibes (PixVerse) 官号 — Meta生态

    # === Priority 3: 竞对官方账号 — 重点关注官方X账号的功能更新 ===
    "Snapchat",         # Snapchat官号
    "OpenAI",           # OpenAI官号 (ChatGPT)
    "soraofficialapp",  # Sora官号
    "pika_labs",        # Pika 官方
    "krea_ai",          # Krea 官方
    "lovart_ai",        # Lovart 官方
    "ElevenCreative",   # ElevenLabs Creative 账号
    "GoogleDeepMind",   # Google DeepMind 官方
    "xai",              # xAI官号 (Grok)
    "Kling_ai",         # 可灵官号
    "Runwayml",         # Runway官号
    "Suno",             # Suno官号
    "Midjourney",       # Midjourney官号
    "capcutapp",        # CapCut官号
    "get_doubao",       # 豆包官号

    # === 功能爆料博主 & 策略分析师 ===
    "nima_owji",        # iOS/App功能爆料
    "AssembleDebug",    # Android功能爆料
    "LindseyGamble_",   # 社交媒体功能分析
    "jonah_manzano",    # 功能爆料
    "ahmedghanem",      # 功能爆料 (重点关注: Edits/MetaAI)
    "wesroth",          # OpenAI产品 (移入MUST_READ以提高优先级)
    "higgsfield",       # AI视频生成
    "LumaLabsAI",       # AI视频生成 (Luma)
    "recraftai",        # AI设计/图像
    "intheworldofai",   # AIGC动态
    "aisearchio",       # AI工具动态
    "imustafasanaul",   # 功能爆料
    "SaadhJawwadh",     # 功能爆料
    "nickysweet857",    # 功能爆料
    "techjalal",        # 功能爆料
    "isajorsergio",     # 功能爆料
    "swak_12",          # 功能爆料
    "dinkin_flickaa",   # 功能爆料
    "billpeeb",         # 功能爆料
    "howfxr",           # X功能爆料
]

ACCOUNTS_FILTERED = {
    # account: (min_likes, min_retweets)  — 任意一个超过门槛即保留
    # === Priority 2: Meta家族官号（已移入MUST_READ的不重复列）===
    "facebook":       (30,   10),    # FB官号，降低门槛（Priority 2）
    # === Priority 3: 竞对媒体/科技媒体 ===
    "elonmusk":       (500,  100),   # 发帖多但大多不相关，高互动才看
    "TechCrunch":     (15,   5),     # 科技媒体，降低门槛捕获并购信息
    "verge":          (15,   5),    # 科技媒体
    "Variety":        (15,   5),    # 娱乐/科技媒体
    "socialmedia2day":(15,   5),    # 社媒专媒
    "xDaily":         (15,   5),    # X动态聚合
    "satopon__":      (30,   10),
    "wongmjane":      (30,   10),    # 知名功能爆料博主
    "aiwarts":        (30,   10),    # AIGC图像/工具动态
    "IndianIdle":     (20,   5),     # 社交应用新功能截图追踪
    "XFreeze":        (20,   5),     # X/Grok UI追踪
    "cb_doge":        (100,  20),    # X/Grok 功能追踪
}

ALL_ACCOUNTS = list(ACCOUNTS_MUST_READ) + list(ACCOUNTS_FILTERED.keys())

# ============ OPT 2: RELEVANCE KEYWORDS (applied at scrape time) ============
RELEVANT_KEYWORDS = [
    # 产品功能通用词
    "feature", "update", "new", "launch", "introducing", "rolling out",
    "available", "test", "beta", "now you can", "coming soon",

    # 内容创作
    "story", "reel", "post", "create", "creator", "edit", "filter",
    "effect", "sticker", "template", "draft", "upload", "clip",

    # 社交互动
    "dm", "direct message", "comment", "like", "share", "follow",
    "follower", "reaction", "chat", "inbox", "notification", "tag",
    "group", "friend", "block", "mute",

    # AI/AIGC 通用词
    "ai ", " ai", "artificial intelligence", "gpt", "llm", "model",
    "generate", "generated", "generation", "chatgpt", "copilot",
    "machine learning", "neural", "chatbot",
    "image generation", "video generation", "generative",
    "text-to-image", "text-to-video", "music generation",

    # ===== 社交平台 =====
    "instagram", "whatsapp", "facebook", "snapchat", "threads",
    "telegram", "discord", "signal", "line app", "imessage",
    "twitter", "tiktok",

    # ===== 创作平台 =====
    "youtube", "spotify", "x premium",

    # ===== AIGC 产品 =====
    # Meta
    "meta ai",
    # xAI
    "grok", "xai",
    # Google
    "gemini", "veo", "google ai",
    # OpenAI
    "openai", "sora", "chatgpt", "dall-e", "dalle",
    # 视频生成
    "vibes", "pixverse", "runway", "vidu", "kling", "可灵",
    # 音乐生成
    "suno", "udio", "mureka",
    # 图像生成
    "midjourney", "stable diffusion",
    # 中文平台
    "快手", "minimax", "海螺", "阿里", "通义", "wan ", "即梦",

    # ===== 图文平台 =====
    "xiaohongshu", "小红书", "reddit", "pinterest",

    # 应用/工具通用
    "app", "tool", "platform", "api", "sdk", "cli", "terminal",
    "edit", "transcript", "tts", "voiceover", "acquisition", "acquire", "merger",
    "plugin", "vfx", "template", "imagine", "redesign", "ui", "ux",
]

# ============ OPT 3: INCREMENTAL - LAST RUN TIMESTAMP ============
STATE_FILE = "scraper_state.json"

def load_last_run_time():
    """Load the timestamp of the last successful run"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                state = json.load(f)
            ts = state.get("last_run_utc")
            if ts:
                dt = datetime.fromisoformat(ts)
                print(f"[Incremental] Last run: {dt.strftime('%Y-%m-%d %H:%M UTC')}")
                return dt
        except:
            pass
    # First run: look back 48h (extended for safety)
    fallback = datetime.now(timezone.utc) - timedelta(hours=48)
    print(f"[Incremental] First run, looking back 48h since: {fallback.strftime('%Y-%m-%d %H:%M UTC')}")
    return fallback

def save_run_time():
    """Save current time as last run timestamp"""
    with open(STATE_FILE, "w") as f:
        json.dump({"last_run_utc": datetime.now(timezone.utc).isoformat()}, f)

# ============ GRAPHQL API ============
USER_BY_SCREENNAME_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True
}

USER_TWEETS_FEATURES = {
    "rweb_lists_timeline_redesign_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
    "interactive_text_enabled": True,
    "responsive_web_text_conversations_enabled": False,
    "longform_notetweets_rich_text_read_enabled": True,
    "responsive_web_enhance_cards_enabled": False
}

session = requests.Session()
session.cookies.update(COOKIES)
session.headers.update(HEADERS)

def get_user_id(username):
    # Updated Query ID (2026-03)
    url = "https://x.com/i/api/graphql/1VOOyvKkiI3FMmkeDNxM9A/UserByScreenName"
    params = {
        "variables": json.dumps({"screen_name": username, "withSafetyModeUserFields": True}),
        "features": json.dumps(USER_BY_SCREENNAME_FEATURES),
        "fieldToggles": json.dumps({"withAuxiliaryUserLabels": False})
    }
    try:
        r = session.get(url, params=params, timeout=15)
        if r.status_code == 200:
            user_result = r.json().get("data", {}).get("user", {}).get("result", {})
            rest_id = user_result.get("rest_id", "")
            if rest_id:
                return rest_id
    except:
        pass
    return None

def get_user_tweets(user_id, count=20):
    # Updated Query ID (2026-03) — from twscrape v0.17.0
    query_ids = [
        "HeWHY26ItCfUmm1e6ITjeA",
    ]
    variables = {
        "userId": user_id,
        "count": count,
        "includePromotedContent": False,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
        "withV2Timeline": True
    }
    for qid in query_ids:
        url = f"https://x.com/i/api/graphql/{qid}/UserTweets"
        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(USER_TWEETS_FEATURES)
        }
        try:
            r = session.get(url, params=params, timeout=15)
            if r.status_code == 200:
                return parse_timeline(r.json())
        except:
            continue
    return []

def parse_timeline(data):
    tweets = []
    try:
        user_result = data.get("data", {}).get("user", {}).get("result", {})
        # 兼容 timeline_v2 和新版 timeline 结构
        tl_data = user_result.get("timeline_v2") or user_result.get("timeline")
        if not tl_data:
            return tweets
        timeline = tl_data.get("timeline", {})

        for instruction in timeline.get("instructions", []):
            # TimelineAddEntries
            if instruction.get("type") == "TimelineAddEntries":
                for entry in instruction.get("entries", []):
                    parsed = _extract_tweet_from_entry(entry.get("content", {}))
                    if parsed:
                        tweets.append(parsed)
            # TimelinePinEntry (置顶推文)
            elif instruction.get("type") == "TimelinePinEntry":
                parsed = _extract_tweet_from_entry(
                    instruction.get("entry", {}).get("content", {})
                )
                if parsed:
                    tweets.append(parsed)
    except Exception as e:
        print(f"  [parse_timeline error] {e}")
    return tweets

def _extract_tweet_from_entry(content):
    """从 entry content 中提取推文，兼容多种结构"""
    try:
        item = content.get("itemContent", {})
        if not item:
            return None
        tw = item.get("tweet_results", {}).get("result", {})
        if tw.get("__typename") == "TweetWithVisibilityResults":
            tw = tw.get("tweet", tw)
        if tw.get("__typename") != "Tweet":
            return None
        return parse_tweet(tw)
    except:
        return None

def parse_tweet(tw):
    try:
        legacy = tw.get("legacy", {})
        if not legacy:
            return None
        text = legacy.get("full_text", "")
        if text.startswith("RT @"):
            return None  # skip pure retweets

        tweet_id = legacy.get("id_str", "")
        created_str = legacy.get("created_at", "")
        created_at = datetime.strptime(created_str, "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=timezone.utc)

        core = tw.get("core", {})
        author_legacy = core.get("user_results", {}).get("result", {}).get("legacy", {})
        author = author_legacy.get("screen_name", "")

        # Extract Media (Images)
        media_urls = []
        extended_entities = tw.get("legacy", {}).get("extended_entities", {})
        media_list = extended_entities.get("media", [])
        for m in media_list:
            if m.get("type") == "photo":
                # Use ?name=orig as per user rules (replacing :orig)
                base_url = m.get("media_url_https", "")
                if ":orig" in base_url:
                    base_url = base_url.replace(":orig", "")
                media_urls.append(base_url + "?name=orig")

        return {
            "id": tweet_id,
            "author": author,
            "text": text,
            "created_at": created_at.isoformat(),
            "url": f"https://x.com/{author}/status/{tweet_id}",
            "likes": legacy.get("favorite_count", 0),
            "retweets": legacy.get("retweet_count", 0),
            "media": media_urls
        }
    except:
        return None

def is_relevant(tweet):
    """OPT 2: keyword filter at scrape time"""
    text_lower = tweet.get("text", "").lower()
    return any(kw in text_lower for kw in RELEVANT_KEYWORDS)

def is_from_monitored_account(tweet):
    """过滤掉转发了非监控账号的推文（author不在我们的列表里）"""
    author = tweet.get("author", "").lower()
    all_lower = [a.lower() for a in ALL_ACCOUNTS]
    return author in all_lower

def passes_engagement_filter(username, tweet):
    """OPT 1: engagement threshold for filtered accounts"""
    if username in ACCOUNTS_MUST_READ:
        return True  # must-read: no filter
    thresholds = ACCOUNTS_FILTERED.get(username)
    if thresholds:
        min_likes, min_rt = thresholds
        return tweet["likes"] >= min_likes or tweet["retweets"] >= min_rt
    return True

def main():
    print("=" * 55)
    print("X Tweet Scraper v3 — Optimized")
    print("=" * 55)

    # OPT 3: load last run time
    since_time = load_last_run_time()

    all_tweets = []
    account_stats = {}

    for username in ALL_ACCOUNTS:
        tier = "must" if username in ACCOUNTS_MUST_READ else "filtered"
        print(f"  @{username} [{tier}] ...", end=" ", flush=True)

        user_id = get_user_id(username)
        if not user_id:
            print("❌ user id failed")
            account_stats[username] = {"status": "failed", "total": 0, "kept": 0}
            time.sleep(0.5)
            continue

        raw_tweets = get_user_tweets(user_id)
        if not raw_tweets:
            # Try once more with a different query ID or just a delay
            time.sleep(2)
            raw_tweets = get_user_tweets(user_id)

        kept = []
        for t in raw_tweets:
            # OPT 3: time filter (incremental)
            try:
                created = datetime.fromisoformat(t["created_at"])
                if created <= since_time:
                    continue
            except:
                continue

            # OPT 2: relevance keyword filter (Only for filtered-tier accounts)
            if username not in ACCOUNTS_MUST_READ and not is_relevant(t):
                continue

            # 过滤非监控账号（转发了其他账号的内容）
            if not is_from_monitored_account(t):
                continue

            # OPT 1: engagement filter for filtered-tier accounts
            if not passes_engagement_filter(username, t):
                continue

            kept.append(t)

        print(f"✅ {len(raw_tweets)} raw → {len(kept)} kept")
        account_stats[username] = {"status": "ok", "total": len(raw_tweets), "kept": len(kept)}
        all_tweets.extend(kept)
        time.sleep(2)  # 增加间隔到2秒，防止频繁触发限流

    # Deduplicate
    seen = set()
    unique = []
    for t in all_tweets:
        if t["id"] not in seen:
            seen.add(t["id"])
            unique.append(t)

    unique.sort(key=lambda x: x["created_at"], reverse=True)

    print(f"\n✅ Total tweets kept: {len(unique)}")
    print(f"   (Since: {since_time.strftime('%Y-%m-%d %H:%M UTC')})")

    # Save
    with open("tweets_raw.json", "w", encoding="utf-8") as f:
        json.dump({
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "since": since_time.isoformat(),
            "total_kept": len(unique),
            "account_stats": account_stats,
            "tweets": unique
        }, f, ensure_ascii=False, indent=2)

    print("Saved → tweets_raw.json")

    # OPT 3: update last run timestamp
    save_run_time()
    print(f"State saved → {STATE_FILE}")

    return unique

if __name__ == "__main__":
    main()
