#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
剪映日报 Bitable 抓取脚本（byted_aime_sdk 版）
- 读取目标日期（北京时间前一天，周一取上周五）的剪映日报记录
- 字段：统计日期（日期型，毫秒时间戳）、新闻摘要、来源
- 输出：jianyingdaily_raw.json
"""

import json
import os
from datetime import datetime, timedelta, timezone

from byted_aime_sdk import call_aime_tool

APP_TOKEN = "SFeus0KAmhjnE8t3ErbcDN2onZc"
TABLE_ID  = "tblI4BK5qRiCa7ov"


def get_target_date():
    """获取目标日期（北京时间前一天，周一取上周五）"""
    tz_cst = timezone(timedelta(hours=8))
    now = datetime.now(tz_cst)
    weekday = now.weekday()  # 0=周一 … 6=周日
    if weekday == 0:          # 周一 → 取上周五
        delta = 3
    elif weekday == 6:        # 周日 → 取上周五
        delta = 2
    elif weekday == 5:        # 周六 → 取上周五
        delta = 1
    else:
        delta = 1
    target = now - timedelta(days=delta)
    return target.strftime("%Y-%m-%d")


def date_to_ts_ms(date_str: str) -> int:
    """YYYY-MM-DD → 北京时间当天 0:00:00 的毫秒时间戳"""
    tz_cst = timezone(timedelta(hours=8))
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz_cst)
    return int(dt.timestamp() * 1000)


def search_records(target_date: str):
    """用过滤器查询指定日期的 bitable 记录"""
    ts_ms = date_to_ts_ms(target_date)
    filter_json = json.dumps({
        "conjunction": "and",
        "conditions": [
            {
                "field_name": "统计日期",
                "operator": "is",
                "value": ["ExactDate", str(ts_ms)]
            }
        ]
    }, ensure_ascii=False)

    all_records = []
    page_token = ""

    while True:
        params = {
            "app_token": APP_TOKEN,
            "table_id":  TABLE_ID,
            "filter":    filter_json,
            "page_size": 200,
        }
        if page_token:
            params["page_token"] = page_token

        resp = call_aime_tool(
            toolset="lark_bitable",
            tool_name="lark_bitable_SearchAppTableRecord",
            parameters=params,
        )

        # resp 可能是字符串或 dict
        if isinstance(resp, str):
            resp = json.loads(resp)

        code = resp.get("code", -1)
        if code != 0:
            print(f"[ERROR] API 返回错误: code={code}, msg={resp.get('msg')}")
            # 如果 SearchAppTableRecord 不存在，降级到 ListAppTableRecord
            return None

        data  = resp.get("data") or {}
        items = data.get("items") or []
        all_records.extend(items)

        if not data.get("has_more"):
            break
        page_token = data.get("page_token") or ""

    return all_records


def list_records_fallback(target_date: str):
    """降级方案：全量拉取，在本地按日期过滤"""
    ts_ms = date_to_ts_ms(target_date)
    # 当天结束时间（+1天）
    ts_ms_end = date_to_ts_ms(
        (datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    )

    all_records = []
    page_token  = ""

    while True:
        params = {
            "app_token": APP_TOKEN,
            "table_id":  TABLE_ID,
            "page_size": 200,
        }
        if page_token:
            params["page_token"] = page_token

        resp = call_aime_tool(
            toolset="lark_bitable",
            tool_name="lark_bitable_ListAppTableRecord",
            parameters=params,
        )

        if isinstance(resp, str):
            resp = json.loads(resp)

        code = resp.get("code", -1)
        if code != 0:
            print(f"[ERROR] ListAppTableRecord 失败: code={code}, msg={resp.get('msg')}")
            break

        data  = resp.get("data") or {}
        items = data.get("items") or []

        for item in items:
            fields = item.get("fields") or {}
            date_field = fields.get("统计日期")
            # 日期字段可能是毫秒时间戳(int)
            if isinstance(date_field, (int, float)):
                if ts_ms <= date_field < ts_ms_end:
                    all_records.append(item)
            elif isinstance(date_field, str) and date_field[:10] == target_date:
                all_records.append(item)

        if not data.get("has_more"):
            break
        page_token = data.get("page_token") or ""

    return all_records


def parse_text_field(val):
    """解析飞书富文本或普通字段"""
    if not val:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        parts = []
        for seg in val:
            if isinstance(seg, dict):
                parts.append(seg.get("text", ""))
            elif isinstance(seg, str):
                parts.append(seg)
        return "".join(parts).strip()
    return str(val)


def main():
    target_date = get_target_date()
    print(f"[INFO] 目标日期：{target_date}")

    # 先尝试 Search API
    records = search_records(target_date)

    if records is None:
        print("[INFO] SearchAppTableRecord 不可用，降级到 List + 本地过滤")
        records = list_records_fallback(target_date)

    print(f"[INFO] 原始记录数：{len(records)}")

    # 调试：打印第一条字段名，帮助验证
    if records:
        sample_fields = list((records[0].get("fields") or {}).keys())
        print(f"[DEBUG] 字段名：{sample_fields}")

    # 转成统一格式
    output_items = []
    for item in records:
        fields  = item.get("fields") or {}
        summary = parse_text_field(fields.get("新闻摘要", ""))
        source  = parse_text_field(fields.get("来源", ""))
        # 来源可能是超链接对象 [{"text":"...","link":"..."}]
        url = ""
        raw_src = fields.get("来源")
        if isinstance(raw_src, list):
            for seg in raw_src:
                if isinstance(seg, dict) and "link" in seg:
                    url = seg["link"]
                    break
        if not url and source.startswith("http"):
            url = source
            source = ""

        if summary:
            output_items.append({
                "source":  "剪映日报",
                "title":   summary[:80],
                "summary": summary,
                "url":     url or source,
                "date":    target_date,
            })

    output = {
        "source":      "jianyingdaily",
        "target_date": target_date,
        "items":       output_items,
    }

    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "jianyingdaily_raw.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[INFO] 完成，共 {len(output_items)} 条 → {out_path}")


if __name__ == "__main__":
    main()
