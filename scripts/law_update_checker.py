#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AI 出海合规管理与法案预警助手 v02
法规来源自动监控脚本

用途：
1. 读取 data/law_source_registry.csv 里的官方来源链接；
2. 请求官方网页 / PDF / API 页面；
3. 记录 HTTP 状态、Last-Modified、ETag、正文 hash、标题等监控指纹；
4. 与上一轮 data/law_monitor_snapshot.csv 对比；
5. 发现疑似变化时，追加写入 data/law_update_log.csv；
6. 由 GitHub Actions 定时运行并自动提交 CSV 变化。

注意：
- 本脚本只做“疑似更新提示”，不直接判断法律义务已变化；
- 所有疑似更新都应进入人工复核流程；
- 部分官网可能反爬、超时或返回动态内容，本脚本会记录 fetch_error 但不中断整体任务。
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SOURCE_FILE = DATA_DIR / "law_source_registry.csv"
SNAPSHOT_FILE = DATA_DIR / "law_monitor_snapshot.csv"
UPDATE_LOG_FILE = DATA_DIR / "law_update_log.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AI-Oversea-Compliance-Monitor/1.0; "
        "+https://github.com/MRJJ1023/ai-oversea-compliance-assistant)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.8",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:200_000]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def fetch_url(url: str, timeout: int = 25) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "http_status": "",
        "content_type": "",
        "etag": "",
        "last_modified": "",
        "page_title": "",
        "content_hash": "",
        "content_length": "",
        "fetch_error": "",
    }
    if not isinstance(url, str) or not url.strip():
        result["fetch_error"] = "empty_url"
        return result
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        result["http_status"] = str(resp.status_code)
        result["content_type"] = resp.headers.get("Content-Type", "")[:160]
        result["etag"] = resp.headers.get("ETag", "")[:160]
        result["last_modified"] = resp.headers.get("Last-Modified", "")[:160]
        raw = resp.content or b""
        result["content_length"] = str(len(raw))

        # HTML 页面优先抽取可读文本，PDF/二进制则直接 hash 二进制内容。
        content_type_lower = result["content_type"].lower()
        if "html" in content_type_lower or "xml" in content_type_lower or raw[:100].lower().find(b"<html") >= 0:
            text = resp.text
            soup = BeautifulSoup(text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            visible_text = normalize_text(soup.get_text(" ", strip=True))
            result["page_title"] = title[:240]
            result["content_hash"] = sha256_text(visible_text)
        else:
            result["content_hash"] = hashlib.sha256(raw).hexdigest()
            result["page_title"] = "binary_or_pdf_content"
    except Exception as exc:  # noqa: BLE001
        result["fetch_error"] = f"{type(exc).__name__}: {str(exc)[:260]}"
    return result


def load_snapshot() -> pd.DataFrame:
    if SNAPSHOT_FILE.exists():
        return pd.read_csv(SNAPSHOT_FILE).fillna("")
    return pd.DataFrame()


def append_updates(update_rows: list[dict[str, Any]]) -> None:
    if not update_rows:
        return
    new_df = pd.DataFrame(update_rows)
    if UPDATE_LOG_FILE.exists():
        old_df = pd.read_csv(UPDATE_LOG_FILE).fillna("")
        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(UPDATE_LOG_FILE, index=False, encoding="utf-8-sig")


def main(mode: str = "check", timeout: int = 25) -> int:
    if not SOURCE_FILE.exists():
        print(f"source file not found: {SOURCE_FILE}", file=sys.stderr)
        return 2

    source_df = pd.read_csv(SOURCE_FILE).fillna("")
    old_snapshot = load_snapshot()
    old_by_key: dict[str, dict[str, Any]] = {}
    if not old_snapshot.empty and "source_key" in old_snapshot.columns:
        old_by_key = {str(row["source_key"]): dict(row) for _, row in old_snapshot.iterrows()}

    new_snapshot_rows: list[dict[str, Any]] = []
    update_rows: list[dict[str, Any]] = []
    now = utc_now()

    for idx, row in source_df.iterrows():
        source_key = str(row.get("source_id", "")).strip() or f"LAW-{idx + 1:03d}"
        jurisdiction = str(row.get("jurisdiction", ""))
        law_name = str(row.get("law_name", ""))
        official_url = str(row.get("official_url", ""))
        monitor = str(row.get("monitoring_method", ""))
        print(f"checking {source_key}: {jurisdiction} | {law_name} | {official_url}")

        fetch = fetch_url(official_url, timeout=timeout)
        snapshot_row: dict[str, Any] = {
            "source_key": source_key,
            "jurisdiction": jurisdiction,
            "law_name": law_name,
            "official_url": official_url,
            "monitoring_method": monitor,
            "checked_at": now,
            **fetch,
        }
        old = old_by_key.get(source_key, {})
        old_hash = str(old.get("content_hash", ""))
        old_etag = str(old.get("etag", ""))
        old_last_modified = str(old.get("last_modified", ""))
        new_hash = str(fetch.get("content_hash", ""))
        new_etag = str(fetch.get("etag", ""))
        new_last_modified = str(fetch.get("last_modified", ""))

        change_fields = []
        if old:
            if old_hash and new_hash and old_hash != new_hash:
                change_fields.append("content_hash")
            if old_etag and new_etag and old_etag != new_etag:
                change_fields.append("etag")
            if old_last_modified and new_last_modified and old_last_modified != new_last_modified:
                change_fields.append("last_modified")

        snapshot_row["change_detected"] = "是" if change_fields else "否"
        snapshot_row["change_fields"] = ";".join(change_fields)
        new_snapshot_rows.append(snapshot_row)

        # 第一次建基线时不追加更新日志，避免一上来全量刷屏。
        if old and change_fields and mode != "initialize":
            update_id = f"AUTO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{source_key}"
            update_rows.append(
                {
                    "update_id": update_id,
                    "jurisdiction": jurisdiction,
                    "law_name": law_name,
                    "source_url": official_url,
                    "detected_date": now,
                    "change_type": "疑似官方来源更新",
                    "change_summary": f"监控字段发生变化：{'; '.join(change_fields)}。本记录仅代表疑似更新，需要人工复核原文内容。",
                    "impact_level": "待评估",
                    "affected_scenarios": str(row.get("applicable_scenarios", "")),
                    "suggested_review_action": "打开官方来源，人工核对是否有新版本、条文修订、指南更新或发布时间变化；必要时更新法规摘要和风险规则库。",
                    "status": "待人工复核",
                }
            )

    pd.DataFrame(new_snapshot_rows).to_csv(SNAPSHOT_FILE, index=False, encoding="utf-8-sig")
    append_updates(update_rows)
    print(f"snapshot written: {SNAPSHOT_FILE}")
    print(f"detected updates: {len(update_rows)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["initialize", "check"], default="check", help="initialize: only build baseline snapshot; check: append suspicious updates when changes are found")
    parser.add_argument("--timeout", type=int, default=25)
    args = parser.parse_args()
    raise SystemExit(main(mode=args.mode, timeout=args.timeout))
