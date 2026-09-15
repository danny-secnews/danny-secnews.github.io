"""RSS 수집 모듈 - 표준 라이브러리만 사용."""
from __future__ import annotations

import gzip
import html
import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (compatible; BohoDailyBot/1.0; +https://github.com/)"
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def fetch(url: str, timeout: int = 25, retries: int = 2) -> bytes | None:
    ctx = ssl.create_default_context()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                    "Accept-Encoding": "gzip",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except Exception as exc:  # noqa: BLE001
            last = exc
    print(f"  [!] fetch 실패: {url} ({last})")
    return None


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def clean_text(value: str | None, limit: int = 220) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = TAG_RE.sub(" ", text)
    text = WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except Exception:  # noqa: BLE001
        pass
    candidate = value.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            dt = datetime.fromisoformat(candidate) if fmt is None else datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            return dt.astimezone(KST)
        except Exception:  # noqa: BLE001
            continue
    return None


def _first(node, names):
    for child in node:
        if strip_ns(child.tag) in names:
            return child
    return None


def parse_feed(raw: bytes, source: str) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        try:
            root = ET.fromstring(raw.decode("utf-8", "ignore").encode("utf-8"))
        except Exception:  # noqa: BLE001
            print(f"  [!] XML 파싱 실패: {source}")
            return []

    entries: list[dict] = []
    nodes = [n for n in root.iter() if strip_ns(n.tag) in ("item", "entry")]
    for node in nodes:
        title_el = _first(node, {"title"})
        title = clean_text(title_el.text if title_el is not None else "", 200)
        if not title:
            continue

        link = ""
        for child in node:
            if strip_ns(child.tag) != "link":
                continue
            if child.get("href"):
                rel = child.get("rel", "alternate")
                if rel == "alternate" or not link:
                    link = child.get("href", "")
            elif child.text:
                link = child.text.strip()
        if not link:
            guid = _first(node, {"guid", "id"})
            if guid is not None and guid.text and guid.text.startswith("http"):
                link = guid.text.strip()
        if not link:
            continue

        summary_el = _first(node, {"description", "summary", "content"})
        summary = clean_text(summary_el.text if summary_el is not None else "")

        date_el = _first(node, {"pubDate", "published", "updated", "date"})
        published = parse_date(date_el.text if date_el is not None else None)

        entries.append(
            {
                "title": title,
                "link": link,
                "summary": summary,
                "source": source,
                "published": published.isoformat() if published else None,
                "published_dt": published,
            }
        )
    return entries


def normalize_title(title: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", title.lower())[:60]


def extract_cves(*texts: str) -> list[str]:
    found: list[str] = []
    for text in texts:
        for cve in re.findall(r"CVE-\d{4}-\d{4,7}", text or "", re.IGNORECASE):
            cve = cve.upper()
            if cve not in found:
                found.append(cve)
    return found[:6]


def collect(config: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(KST)
    site = config["site"]
    cutoff = now - timedelta(hours=int(site.get("lookback_hours", 30)))
    limit = int(site.get("max_items_per_category", 12))
    keywords = [k.lower() for k in config.get("highlight_keywords", [])]

    result = {"generated_at": now.isoformat(), "date": now.strftime("%Y-%m-%d"), "categories": []}
    seen: set[str] = set()

    for category in config["categories"]:
        items: list[dict] = []
        for feed in category["feeds"]:
            print(f"  · {category['name']} / {feed['name']}")
            raw = fetch(feed["url"])
            if not raw:
                continue
            for entry in parse_feed(raw, feed["name"]):
                key = normalize_title(entry["title"])
                if not key or key in seen:
                    continue
                dt = entry.pop("published_dt", None)
                if dt is not None and dt < cutoff:
                    continue
                if dt is None:
                    entry["published"] = now.isoformat()
                    dt = now
                seen.add(key)
                blob = f"{entry['title']} {entry['summary']}".lower()
                entry["highlight"] = any(k in blob for k in keywords)
                entry["cves"] = extract_cves(entry["title"], entry["summary"])
                entry["sort_key"] = dt.isoformat()
                items.append(entry)

        items.sort(key=lambda e: (not e["highlight"], e["sort_key"]), reverse=False)
        items.sort(key=lambda e: e["sort_key"], reverse=True)
        items.sort(key=lambda e: not e["highlight"])
        items = items[:limit]
        for item in items:
            item.pop("sort_key", None)

        result["categories"].append(
            {"id": category["id"], "name": category["name"], "emoji": category.get("emoji", "•"), "items": items}
        )
        print(f"    -> {len(items)}건")

    result["total"] = sum(len(c["items"]) for c in result["categories"])
    return result


if __name__ == "__main__":
    with open("feeds.json", encoding="utf-8") as fp:
        cfg = json.load(fp)
    print(json.dumps(collect(cfg), ensure_ascii=False, indent=2)[:2000])
