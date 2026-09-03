# -*- coding: utf-8 -*-
"""检查当前微信编辑器状态，尝试找到 ProSeMirror 实例"""
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

    print(f"URL: {page.url[:100]}")

    # 检查 ProseMirror 实例
    result = page.evaluate("""() => {
        const info = {};
        
        // 方法1: 检查 window 上的 ProseMirror 相关对象
        info.pm = {};
        info.pm.hasPM = typeof window.ProseMirror !== 'undefined';
        info.pm.keys = Object.keys(window).filter(k => k.toLowerCase().includes('prose'));
        
        // 方法2: 检查编辑器 DOM 元素的 __vue__ / __reactFiber__ / pmViewDesc
        const editors = document.querySelectorAll('.ProseMirror');
        info.editors = [];
        editors.forEach((el, i) => {
            const d = {
                idx: i,
                textLen: el.textContent.length,
                innerHTML_len: el.innerHTML.length,
                hasPmViewDesc: !!el.pmViewDesc,
                pmViewDescKeys: el.pmViewDesc ? Object.keys(el.pmViewDesc) : [],
                hasVue: !!el.__vue__,
                hasReact: !!el.__reactFiber__,
                firstChild: el.firstChild ? el.firstChild.nodeName : null,
                imgCount: el.querySelectorAll('img').length,
                imgs: []
            };
            el.querySelectorAll('img').forEach((img, j) => {
                d.imgs.push({
                    j: j,
                    src: img.src.substring(0, 80),
                    w: img.naturalWidth,
                    h: img.naturalHeight,
                    complete: img.complete
                });
            });
            info.editors.push(d);
        });
        
        // 方法3: 尝试找 WeChat 编辑器的全局 API
        info.wx = {};
        info.wx.hasWxEditor = typeof window.wxEditor !== 'undefined';
        info.wx.wxEditorKeys = window.wxEditor ? Object.keys(window.wxEditor) : [];
        info.wx.hasUe = typeof window.UE !== 'undefined';
        info.wx.hasUeV2 = typeof window.UE_V2 !== 'undefined';
        
        return info;
    }""")

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
