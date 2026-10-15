"""Recover damaged ziwei.my archives from their public WordPress article IDs.

The old files already contain U+FFFD, so guessing/reversing that encoding loses
characters. Fetch the publisher's current UTF-8 body instead, record its revision,
keep the original capture date, and back up every replaced file outside Git.
No language model, credentials or private chart data is used.

    python scripts/repair_ziwei_archive.py --apply
    python scripts/repair_ziwei_archive.py --limit 3   # fetch/validate only
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, unquote
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.ziwei.my"
UA = "ChinaExpe-ArchiveRepair/1.0"
MOJI = re.compile(r"(?:[äåæçèé](?:[^\u3400-\u9fff\s]|\xa0){1,2}){2}|Ã[\x80-\u00bf]|Â[\x80-\u00bf]")


def damaged(text: str) -> bool:
    return "\ufffd" in text or bool(MOJI.search(text))


class ArticleText(HTMLParser):
    """Extract only publisher body markup; keep inline words and table boundaries."""
    BLOCKS = {"p", "div", "section", "article", "li", "ul", "ol", "blockquote",
              "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "pre", "figure"}
    SKIP = {"script", "style", "noscript", "nav", "form"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip.append(tag)
        if self.skip:
            return
        if tag in self.BLOCKS or tag in {"br", "hr"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")
        elif tag == "img":
            alt = dict(attrs).get("alt", "").strip()
            if alt:
                self.parts.append(f" [图片：{alt}] ")

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

    def text(self):
        lines = [re.sub(r"[ \t\r\f\v\xa0]+", " ", ln).strip() for ln in "".join(self.parts).splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def to_text(markup: str) -> str:
    parser = ArticleText()
    parser.feed(markup)
    return parser.text()


def normal_url(url):
    parsed = urlsplit(url)
    if parsed.hostname not in ("ziwei.my", "www.ziwei.my") or parsed.scheme not in ("http", "https"):
        raise ValueError("source is not a public ziwei.my URL")
    return unquote(parsed.path).rstrip("/") or "/"


def fetch(url):
    normal_url(url)
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}), timeout=60) as response:
                normal_url(response.url)
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                # Do not trust a guessed HTTP charset and never replace undecodable bytes.
                return raw.decode("utf-8-sig")
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = exc.headers.get("Retry-After", "")
            time.sleep(min(int(delay), 60) if delay.isdigit() else 2 ** (attempt + 1))
        except (TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def archive_entry(path, root):
    text = path.read_text(encoding="utf-8")
    if not damaged(text):
        return None
    source = re.search(r"^来源:\s*(\S+)", text, re.M)
    captured = re.search(r"^抓取时间:\s*(.+)$", text, re.M)
    if not source:
        raise ValueError(f"missing source: {path.relative_to(root)}")
    normal_url(source[1])
    original_html = path.with_suffix(".html")
    doc = original_html.read_text(encoding="utf-8") if original_html.exists() else ""
    ids = re.findall(r"\b(?:postid-|page-id-|id=[\"']post-)(\d+)", doc)
    return {"file": str(path.relative_to(root)), "source": source[1], "captured": captured[1] if captured else "未知",
            "id": int(ids[0]) if ids else None, "before_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_record(entry, record):
    if record.get("id") != entry["id"]:
        raise ValueError("article ID mismatch")
    # WordPress keeps the article ID when an author changes its permalink.
    # Accept that move on the same site and retain both URLs in the audit trail.
    normal_url(record.get("link", ""))
    normal_url(entry["source"])
    if record.get("content", {}).get("protected"):
        raise ValueError("password protected article")
    title = to_text(record["title"]["rendered"])
    body = to_text(record["content"]["rendered"])
    if not title or len(body) < 80 or damaged(title + body):
        raise ValueError("empty, truncated or still-damaged publisher body")
    if len(re.findall(r"[\u3400-\u9fff]", body)) < 20:
        raise ValueError("publisher body has too little Chinese text")
    return title, body


def restored_text(entry, record, repaired_at):
    title, body = validate_record(entry, record)
    sep = "=" * 60
    return (f"{sep}\n标题: {title}\n来源: {record['link']}\n抓取时间: {entry['captured']}\n原存档来源: {entry['source']}\n"
            f"修复时间: {repaired_at}\n原站更新时间: {record.get('modified', '未知')}\n"
            f"恢复方式: 原站 WordPress UTF-8 正文（文章 {entry['id']}）；内容以修复时原站版本为准\n"
            f"{sep}\n\n{body}\n")


def write_recovery(root, backup, entry, record, repaired_at):
    target = root / entry["file"]
    text = restored_text(entry, record, repaired_at)
    # Copy before touching either file; retries never overwrite an earlier backup.
    for path in (target, target.with_suffix(".html")):
        saved = backup / path.relative_to(root)
        if path.exists() and not saved.exists():
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
    title = to_text(record["title"]["rendered"])
    doc = (f'<!doctype html><html lang="zh"><head><meta charset="utf-8">'
           f'<title>{html.escape(title)}</title><link rel="canonical" href="{html.escape(record["link"], quote=True)}">'
           f'</head><body class="postid-{entry["id"]}"><article>{record["content"]["rendered"]}</article></body></html>')
    for path, value in ((target, text), (target.with_suffix(".html"), doc)):
        temporary = path.with_name(path.name + ".repair-tmp")
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    return {**entry, "after_sha256": hashlib.sha256(text.encode()).hexdigest(), "title": title,
            "source_modified": record.get("modified"), "repaired_at": repaired_at}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data/maintenance/ziwei-encoding")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    root, cache = args.root.resolve(), args.cache_dir.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    entries = [entry for p in sorted((root / "knowledge_base").rglob("*.txt")) if (entry := archive_entry(p, root))]
    entries = entries[:args.limit] if args.limit else entries
    (cache / "pending.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Damaged archives: {len(entries)}", flush=True)
    if not entries:
        return
    robots = RobotFileParser()
    robots.parse(fetch(BASE + "/robots.txt").splitlines())
    records = {}
    for entry in entries:
        f = cache / f"article-{entry['id']}.json"
        if f.exists():
            records[entry["id"]] = json.loads(f.read_text(encoding="utf-8"))

    def get_batch(kind, ids):
        url = BASE + f"/wp-json/wp/v2/{kind}?" + urlencode({"include": ",".join(map(str, ids)), "per_page": 100,
                "_fields": "id,link,title,content,modified"})
        if not robots.can_fetch(UA, url):
            raise ValueError("robots.txt disallows retrieval")
        time.sleep(0.6)
        data = json.loads(fetch(url))
        if not isinstance(data, list):
            raise ValueError("WordPress returned a non-list response")
        return data

    for kind in ("posts", "pages"):
        missing = sorted({e["id"] for e in entries if e["id"] and e["id"] not in records})
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = {pool.submit(get_batch, kind, missing[i:i+100]): i for i in range(0, len(missing), 100)}
            for job in as_completed(jobs):
                try:
                    for row in job.result():
                        records[row["id"]] = row
                        (cache / f"article-{row['id']}.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
                    print(f"{kind}: cached {len(records)}/{len(entries)}", flush=True)
                except Exception as exc:
                    print(f"{kind} batch {jobs[job]} failed: {exc}", flush=True)
    report_path = cache / "report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {"repaired": [], "failed": []}
    report["failed"] = []
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for entry in entries:
        try:
            record = records.get(entry["id"])
            if not record:
                raise ValueError("article not returned by public posts/pages API")
            validate_record(entry, record)
            if args.apply:
                report["repaired"].append(write_recovery(root, cache / "backup", entry, record, stamp))
        except Exception as exc:
            report["failed"].append({**entry, "error": str(exc)})
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"applied_total": len(report["repaired"]), "failed": len(report["failed"]), "report": str(report_path)}, ensure_ascii=False), flush=True)
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
