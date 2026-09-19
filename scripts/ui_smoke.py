"""Playwright smoke test for the UI (desktop + phone matrix).

Usage: python scripts/ui_smoke.py [base_url]
The person shown is $SMOKE_PID, or the first person the server lists.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8766"


def _pick_pid():
    if os.environ.get("SMOKE_PID"):
        return os.environ["SMOKE_PID"]
    with urllib.request.urlopen(BASE + "/api/people", timeout=10) as r:
        people = json.loads(r.read().decode("utf-8"))
    return people[0]["id"]


PID = _pick_pid()
OUT = Path(__file__).resolve().parent.parent / "data" / "screens"
OUT.mkdir(parents=True, exist_ok=True)

errors = []
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print("  !! FAIL:", msg)


def desktop(b):
    pg = b.new_page(viewport={"width": 1500, "height": 900})
    pg.on("pageerror", lambda e: errors.append("desktop: " + str(e)))
    pg.goto(BASE + f"/#/p/{PID}/ziwei", wait_until="networkidle")
    pg.wait_for_selector("#palace-0", timeout=15000)
    pg.wait_for_timeout(600)
    pg.screenshot(path=str(OUT / "ziwei.png"))
    print("desktop palaces:", pg.locator(".palace").count(), "chips:", pg.locator(".chip").count())
    check(pg.locator("#zw-center").is_visible(), "desktop centre block visible")
    check(not pg.locator("#zw-head").is_visible(), "desktop head bar hidden")
    pg.click("#palace-7"); pg.wait_for_timeout(300)
    check(pg.locator("#context-tags .context-tag").count() == 4, "palace click -> 4 reference bubbles (本宫/对宫/三合×2)")
    check(pg.locator("#zw-svg .link-tri").count() == 0, "dashed links off by default")
    check(pg.locator(".layer-btn.active[data-layer='minor']").count() == 1 and pg.locator(".layer-btn.active[data-layer='sihua']").count() == 1, "四化+小星 on by default")
    check(pg.locator(".layer-btn.active[data-layer='sanhe'], .layer-btn.active[data-layer='feixing'], .layer-btn.active[data-layer='links']").count() == 0, "三合/飞星/虚线 off by default")
    pg.click(".layer-btn[data-layer='links']"); pg.wait_for_timeout(300)
    check(pg.locator("#zw-svg .link-tri").count() == 3 and pg.locator("#zw-svg .link-opp").count() == 1, "虚线 layer draws dashed 三合/对宫 links")
    check(not pg.locator("#modal-palace").is_visible(), "palace click does not open a modal")
    pg.locator("#context-tags .context-tag .remove-tag").nth(3).click(); pg.wait_for_timeout(100)
    check(pg.locator("#context-tags .context-tag").count() == 3, "a single bubble can be removed")
    pg.click(".layer-btn[data-layer='feixing']"); pg.click(".layer-btn[data-layer='sanhe']"); pg.wait_for_timeout(300)
    print("  svg paths:", pg.locator("#zw-svg path").count(), "sanhe:", pg.locator(".palace.sanhe-tri").count(), pg.locator(".palace.sanhe-opp").count())
    check(pg.locator("#zw-svg path").count() >= 4, "feixing arrows drawn")
    pg.screenshot(path=str(OUT / "ziwei-layers.png"))
    pg.locator(".strip").nth(0).locator(".chip").nth(3).click(); pg.wait_for_timeout(500)
    pg.locator(".strip").nth(1).locator(".chip").nth(3).click(); pg.wait_for_timeout(500)
    pg.locator(".strip").nth(2).locator(".chip").nth(4).click(); pg.wait_for_timeout(500)
    pg.locator(".strip").nth(3).locator(".chip").nth(0).click(); pg.wait_for_timeout(500)
    print("  level badges:", pg.locator(".hua.lv").count(), "strips:", pg.locator(".strip").count())
    check(pg.locator(".strip").count() == 5, "5 strips after selecting a day")
    pg.screenshot(path=str(OUT / "ziwei-levels.png"))
    pg.locator("#palace-7 .p-name").click(); pg.wait_for_timeout(300)
    print("  modal:", pg.locator("#modal-palace-title").inner_text())
    pg.keyboard.press("Escape")
    pg.click(".tab-btn[data-chart='bazi']")
    pg.wait_for_selector(".bz-table", timeout=15000); pg.wait_for_timeout(600)
    print("  bazi rows:", pg.locator(".bz-table tbody tr").count(), "cards:", pg.locator(".bz-card").count(), "strips:", pg.locator(".strip").count())
    pg.screenshot(path=str(OUT / "bazi.png"))
    pg.click("#btn-edit-person"); pg.wait_for_timeout(500)
    print("  form name:", pg.input_value("#pf-name"), "settings selects:", pg.locator(".pf-setting").count())
    pg.keyboard.press("Escape")
    r = pg.request.get(BASE + "/manifest.webmanifest")
    check(r.status == 200, "manifest served")
    pg.close()


def phone(b, name, w, h):
    pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg.on("pageerror", lambda e: errors.append(f"{name}: {e}"))
    pg.goto(BASE + f"/#/p/{PID}/ziwei", wait_until="networkidle")
    pg.wait_for_selector("#palace-0", timeout=15000); pg.wait_for_timeout(700)
    print(f"phone {name} {w}x{h}")
    check(pg.locator("#pane-left.collapsed").count() == 1 and pg.locator("#pane-right.collapsed").count() == 1, f"{name}: drawers closed")
    compact = w <= 700
    if compact:
        check(pg.locator("#zw-head").is_visible(), f"{name}: head bar visible")
        check(not pg.locator("#zw-center").is_visible(), f"{name}: centre block hidden in compact mode")
        # palace names on one line
        for i in range(12):
            box = pg.locator(f"#palace-{i} .p-name").bounding_box()
            check(box and box["height"] < 22, f"{name}: palace {i} name single line")
        gh = pg.locator("#zw-grid").bounding_box()["height"]
        check(gh <= h * 0.8, f"{name}: compact grid height {gh:.0f} <= 80% of viewport {h}")
        check(pg.locator(".strip-wrap.collapsed").count() == 1, f"{name}: strips collapsed by default")
        pg.screenshot(path=str(OUT / f"{name}-ziwei.png"))
        # head bar expand
        pg.click("#zw-head .zh-sum"); pg.wait_for_timeout(200)
        check(pg.locator("#zw-head.open").count() == 1, f"{name}: head bar expands")
        pg.click("#zw-head .zh-sum")
        # tap palace -> 三合 links + reference bubbles; tap palace name -> bottom sheet
        pg.click("#palace-7"); pg.wait_for_timeout(400)
        check(pg.locator("#zw-svg .link-tri").count() == 0, f"{name}: no dashed links by default")
        check(pg.locator("#context-tags .context-tag").count() == 4, f"{name}: 4 reference bubbles")
        pg.screenshot(path=str(OUT / f"{name}-links.png"))
        pg.click("#palace-7 .p-name"); pg.wait_for_timeout(400)
        check(pg.locator("#modal-palace").is_visible(), f"{name}: tap palace name opens sheet")
        pg.screenshot(path=str(OUT / f"{name}-sheet.png"))
        pg.click("#modal-palace .pd-actions .btn-secondary >> nth=0"); pg.wait_for_timeout(400)   # 飞星
        check(pg.locator("#zw-svg path").count() >= 4, f"{name}: feixing arrows in compact mode")
        # strips expand + pick
        pg.click(".strip-handle"); pg.wait_for_timeout(300)
        check(pg.locator(".strip-wrap.collapsed").count() == 0, f"{name}: strips expand")
        pg.locator(".strip").nth(0).locator(".chip").nth(3).click(); pg.wait_for_timeout(500)
        check(pg.locator(".strip").count() >= 2, f"{name}: yearly strip appears")
        pg.screenshot(path=str(OUT / f"{name}-strips.png"))
        # zoom mode
        pg.click("#btn-zoom"); pg.wait_for_timeout(400)
        check(pg.locator("#app.zoomed").count() == 1, f"{name}: zoom toggled")
        ww = pg.locator(".zw-wrap").bounding_box()["width"]
        check(ww >= 770, f"{name}: zoomed board width {ww:.0f} >= 770")
        check(pg.locator("#zw-center").is_visible(), f"{name}: centre block visible when zoomed")
        pg.screenshot(path=str(OUT / f"{name}-zoomed.png"))
        pg.click("#btn-zoom"); pg.wait_for_timeout(200)
    else:
        check(pg.locator("#zw-center").is_visible(), f"{name}: full board on landscape/tablet")
        pg.screenshot(path=str(OUT / f"{name}-ziwei.png"))
    # chat drawer
    pg.click("#btn-open-right"); pg.wait_for_timeout(400)
    check(pg.locator("#pane-right.collapsed").count() == 0, f"{name}: chat drawer opens")
    pg.screenshot(path=str(OUT / f"{name}-chat.png"))
    pg.click("#pane-right .only-mobile" if compact else "#pane-right .btn-icon"); pg.wait_for_timeout(300)
    check(pg.locator("#pane-right.collapsed").count() == 1, f"{name}: chat drawer closes")
    # bazi
    pg.click(".tab-btn[data-chart='bazi']"); pg.wait_for_selector(".bz-table", timeout=15000); pg.wait_for_timeout(600)
    check(pg.locator(".bz-card").count() == 5, f"{name}: 5 bazi cards")
    if compact:
        check(pg.locator(".bz-ss .more").count() >= 1, f"{name}: 神煞 +n present")
        pg.click(".bz-ss .more >> nth=0"); pg.wait_for_timeout(300)
        check(pg.locator("#modal-info").is_visible(), f"{name}: 神煞 sheet opens")
        pg.keyboard.press("Escape")
    pg.screenshot(path=str(OUT / f"{name}-bazi.png"))
    pg.close()


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        desktop(b)
        phone(b, "iphone", 375, 812)
        phone(b, "android", 412, 915)
        phone(b, "iphone-max", 430, 932)
        phone(b, "landscape", 812, 375)
        b.close()
    print("console/page errors:", errors)
    print("failures:", failures or "none")
    if errors or failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
