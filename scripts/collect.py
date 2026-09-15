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
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def fetch(url: str, timeout: int = 15, retries: int = 1) -> bytes | None:
    ctx = ssl.create_default_context()
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
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
            if ":" not in value and (dt.hour, dt.minute, dt.second) == (0,0,0):
                dt = dt.replace(hour=23, minute=59)
            return dt.astimezone(KST)
        except Exception:  # noqa: BLE001
            continue
    return None


def _first(node, names):
    for child in node:
        if strip_ns(child.tag) in names:
            return child
    return None


DECL_RE = re.compile(rb"<\?xml[^>]*?encoding\s*=\s*[\"']([A-Za-z0-9_.\-]+)[\"']")


def to_text(raw: bytes) -> str | None:
    # Decode bytes to str. Handles EUC-KR / CP949 used by Korean media sites.
    # Python's XML parser (expat) supports only UTF-8, UTF-16, ISO-8859-1 and
    # US-ASCII, so decode here and strip the XML declaration before parsing.
    match = DECL_RE.search(raw[:300])
    declared = match.group(1).decode("ascii", "ignore").lower() if match else None

    candidates: list[str] = []
    if declared:
        candidates.append(declared)
    for codec in ("utf-8", "cp949", "euc-kr", "latin-1"):
        if codec not in candidates:
            candidates.append(codec)

    for codec in candidates:
        try:
            text = raw.decode(codec)
        except (UnicodeDecodeError, LookupError):
            continue
        return re.sub(r"^\s*<\?xml.*?\?>", "", text, count=1, flags=re.S).strip()
    return None


def parse_feed(raw: bytes, source: str) -> list[dict]:
    text = to_text(raw)
    if not text:
        print(f"  [!] decode failed: {source}")
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        print(f"  [!] XML parse failed: {source} ({exc})")
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
        required = [k.lower() for k in categoty.get("require_keywords",[])]
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
