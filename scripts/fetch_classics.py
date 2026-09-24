"""Download public-domain 命理 classics into data/classics as whole books.

Source: 算准网 (suanzhun.net), which publishes each classic chapter by chapter.
The texts themselves are Ming/Qing public domain works.  One polite request at
a time, with a delay; re-runs skip books that already exist unless --force.

    python scripts/fetch_classics.py                 # the default book list
    python scripts/fetch_classics.py --only ditiansuichanwei --force
"""
from __future__ import annotations

import argparse
import html
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "classics"
BASE = "https://www.suanzhun.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
DELAY = 0.7

# slug -> (书名, 作者/版本, 目标目录, 说明)
BOOKS = {
    "zipingzhenpingzhu": ("子平真诠评注", "沈孝瞻 原著，徐乐吾 评注（清/民国）", "03-子平",
                          "格局与用神的系统之作，喜忌用神的主线"),
    "ditiansuichanwei": ("滴天髓阐微", "刘基 原著，任铁樵 注（清）", "03-子平",
                         "体用、喜忌、旺衰的经典，命理推理的深度范本"),
    # 注意：算准网与中华典藏都只有卷首五行总论，按月令逐条的正文需另外获取，见 data/classics/书单.md
    "qiongtongbaojian": ("穷通宝鉴", "余春台 辑（原名栏江网）", "03-子平",
                         "调候用神；此处只有卷首五行总论，正文缺"),
    "sanmingtonghui": ("三命通会", "万民英（明）", "03-子平",
                       "体系最全的总论，神煞、纳音、格局的主要出处，四库全书收录"),
    "shenfengtongkao": ("神峰通考", "张楠（明）", "03-子平",
                        "病药说与形冲合害的实务讨论"),
    "xingpinghuihai": ("星平会海", "水中龙（明）", "03-子平",
                       "星命合参，神煞系统的另一主要来源"),
}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def chapter_links(slug: str) -> list[tuple[str, str]]:
    """[(title, url)] in reading order, walking the paginated index."""
    seen, out = set(), []
    page, url = 1, f"{BASE}/dianji/{slug}/"
    while url:
        doc = get(url)
        for m in re.finditer(r'href="(/book/(\d+)\.html)"[^>]*>([^<]{2,60})</a>', doc):
            href, _id, title = m.group(1), m.group(2), html.unescape(m.group(3)).strip()
            if href in seen:
                continue
            seen.add(href)
            out.append((title, BASE + href))
        page += 1
        nxt = f"{BASE}/dianji/{slug}/index_{page}.html"
        url = nxt if f"index_{page}.html" in doc else None
        time.sleep(DELAY)
    return out


NAV = re.compile(r"(上一篇|下一篇|相关阅读|版权|Copyright|算准网|微信|扫码|返回|评论)")


def chapter_text(url: str) -> str:
    doc = get(url)
    doc = re.sub(r"(?is)<(script|style).*?</\1>", "", doc)
    body = html.unescape(re.sub(r"(?s)<[^>]+>", "\n", doc))
    lines = [ln.strip() for ln in body.splitlines()]
    out, started = [], False
    for ln in lines:
        if not started:
            started = ln.startswith("日期:") or ln.startswith("日期：")
            continue
        if NAV.search(ln):
            break
        if len(ln) > 8 and not ln.endswith('">'):
            out.append(ln)
    return "\n\n".join(out)


def fetch_book(slug: str, force: bool = False) -> Path | None:
    title, author, cat, note = BOOKS[slug]
    target = OUT / cat / f"{title}.md"
    if target.exists() and not force:
        print(f"skip {title} (exists)")
        return target
    links = chapter_links(slug)
    if not links:
        print(f"!! {title}: no chapters found")
        return None
    print(f"{title}: {len(links)} chapters")
    parts = [f"# {title}\n\n> {author}\n> {note}\n> 下载自 {BASE}/dianji/{slug}/ ，"
             f"共 {len(links)} 篇，原文为公有领域古籍。\n> 引用时写明书名与篇名。\n\n---\n"]
    for i, (ctitle, curl) in enumerate(links, 1):
        try:
            text = chapter_text(curl)
        except Exception as e:
            print(f"   !! {ctitle}: {e}")
            continue
        if text:
            parts.append(f"## {ctitle}\n\n{text}")
        if i % 20 == 0:
            print(f"   {i}/{len(links)}")
        time.sleep(DELAY)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n\n".join(parts), encoding="utf-8")
    print(f"   -> {target} ({target.stat().st_size // 1024} KB)")
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="slugs to fetch (default: all)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    for slug in (a.only or list(BOOKS)):
        if slug not in BOOKS:
            print("unknown slug:", slug)
            continue
        fetch_book(slug, a.force)
