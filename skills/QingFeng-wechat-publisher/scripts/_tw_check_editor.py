# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    page = None
    for pg in browser.contexts[0].pages:
        if 'appmsg_edit' in pg.url:
            page = pg
            break
    if not page:
        print("No editor page found")
        sys.exit(1)

    result = page.evaluate("""() => {
        const editors = document.querySelectorAll('.ProseMirror');
        const info = [];
        editors.forEach((el, i) => {
            info.push({
                idx: i,
                textLen: el.textContent.length,
                htmlLen: el.innerHTML.length,
                htmlPreview: el.innerHTML.substring(0, 500),
                imgCount: el.querySelectorAll('img').length,
                pCount: el.querySelectorAll('p').length,
                sectionCount: el.querySelectorAll('section').length
            });
        });
        return info;
    }""")

    for r in result:
        print(f"ProseMirror[{r['idx']}]: text={r['textLen']} chars, imgs={r['imgCount']}, ps={r['pCount']}, sections={r['sectionCount']}")
        print(f"  HTML preview: {r['htmlPreview'][:300]}")
        print()
