#!/usr/bin/env python3
"""Automated accessibility check of a rendered Lynx tool board (Playwright).

Run with the shared browser runtime:

  PLAYWRIGHT_BROWSERS_PATH=$NOOBIA/common/runtime/playwright \\
    $NOOBIA/common/runtime/web-venv/bin/python lynx/tools/ui/check_board_a11y.py BOARD.html

For light and dark colour schemes, at 1200 px and 390 px widths, it reports:
- WCAG 2.x contrast of every visible text element against its effective
  background (normal text needs 4.5:1, large text 3:1);
- the heading outline and any skipped levels;
- landmarks, and whether every focusable element is reached by Tab and shows
  a visible focus indicator;
- horizontal overflow;
- forbidden elements (script, form, button, input, iframe, remote URLs).

Prints one JSON object and exits 1 if any check fails. It checks only the
page; it says nothing about Lynx's hardware.
"""

import json
import sys

from playwright.sync_api import sync_playwright

PROBE = r"""
() => {
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(',').map(s => parseFloat(s)); return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}; };
  const lum = c => { const f = v => { v/=255; return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); };
    return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b); };
  const blend = (top, bottom) => ({r: top.r*top.a + bottom.r*(1-top.a),
    g: top.g*top.a + bottom.g*(1-top.a), b: top.b*top.a + bottom.b*(1-top.a), a: 1});
  const background = el => { const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let base = {r:255,g:255,b:255,a:1}; for (let i = layers.length-1; i>=0; i--) base = blend(layers[i], base);
    return base; };
  const results = [];
  for (const el of document.querySelectorAll('body *')) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const st = getComputedStyle(el); const rect = el.getBoundingClientRect();
    if (st.visibility === 'hidden' || st.display === 'none' || rect.width === 0) continue;
    const fg = parse(st.color); const bg = background(el);
    const c = blend(fg, bg); const l1 = lum(c), l2 = lum(bg);
    const ratio = (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
    const size = parseFloat(st.fontSize); const bold = parseInt(st.fontWeight) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    results.push({tag: el.tagName.toLowerCase(), cls: el.className || '', text: el.textContent.trim().slice(0,40),
                  ratio: Math.round(ratio*100)/100, need: large ? 3 : 4.5});
  }
  const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h => ({level: +h.tagName[1], text: h.textContent.trim().slice(0,50)}));
  const landmarks = [...document.querySelectorAll('main,header,footer,nav,section[aria-labelledby],[role]')].map(e => e.tagName.toLowerCase() + (e.getAttribute('role') ? '[role='+e.getAttribute('role')+']' : ''));
  const focusables = [...document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')].length;
  return {contrast: results, headings, landmarks, focusables,
          overflow: document.documentElement.scrollWidth > innerWidth,
          lang: document.documentElement.lang, title: document.title,
          forbidden: [...document.querySelectorAll('script,form,button,input,iframe,object,embed')].length,
          remote: [...document.querySelectorAll('[src],[href]')].filter(e => /^(https?:)?\/\//.test(e.getAttribute('src')||e.getAttribute('href'))).length};
}
"""


def check(path):
    report = {"board": path, "views": {}, "failures": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("light", "dark"):
            for width in (1200, 390):
                page = browser.new_page(viewport={"width": width, "height": 900},
                                        color_scheme=scheme)
                page.goto("file://" + path)
                data = page.evaluate(PROBE)
                view = f"{scheme}-{width}"
                low = [c for c in data["contrast"] if c["ratio"] < c["need"]]
                levels = [h["level"] for h in data["headings"]]
                skips = [f"h{a}->h{b}" for a, b in zip(levels, levels[1:]) if b > a + 1]
                # keyboard: Tab through every focusable and require a visible outline
                unfocused, invisible = 0, 0
                for _ in range(data["focusables"]):
                    page.keyboard.press("Tab")
                    info = page.evaluate("""() => { const e = document.activeElement;
                        if (!e || e === document.body) return null;
                        const s = getComputedStyle(e);
                        return {outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0,
                                shadow: s.boxShadow !== 'none'}; }""")
                    if info is None:
                        unfocused += 1
                    elif not (info["outline"] or info["shadow"]):
                        invisible += 1
                report["views"][view] = {
                    "text_elements": len(data["contrast"]),
                    "min_contrast": min((c["ratio"] for c in data["contrast"]), default=None),
                    "low_contrast": low[:10], "heading_skips": skips,
                    "headings": len(levels), "h1": levels.count(1),
                    "landmarks": sorted(set(data["landmarks"])),
                    "focusables": data["focusables"], "tab_unreached": unfocused,
                    "focus_invisible": invisible, "overflow": data["overflow"],
                    "lang": data["lang"], "title": data["title"],
                    "forbidden": data["forbidden"], "remote": data["remote"]}
                v = report["views"][view]
                if low:
                    report["failures"].append(f"{view}: {len(low)} text elements below contrast")
                if skips or v["h1"] != 1:
                    report["failures"].append(f"{view}: heading outline {skips or 'h1 count'}")
                if "main" not in v["landmarks"]:
                    report["failures"].append(f"{view}: no main landmark")
                if unfocused or invisible:
                    report["failures"].append(f"{view}: keyboard focus problems")
                if v["overflow"]:
                    report["failures"].append(f"{view}: horizontal overflow")
                if v["forbidden"] or v["remote"]:
                    report["failures"].append(f"{view}: forbidden or remote elements")
                if not v["lang"] or not v["title"]:
                    report["failures"].append(f"{view}: missing lang or title")
                page.close()
        browser.close()
    report["ok"] = not report["failures"]
    return report


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_board_a11y.py BOARD.html")
    result = check(sys.argv[1])
    print(json.dumps(result, indent=1))
    sys.exit(0 if result["ok"] else 1)
