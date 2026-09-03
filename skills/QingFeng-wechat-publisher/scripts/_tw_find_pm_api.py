# -*- coding: utf-8 -*-
"""尝试通过 ProSeMirror API 注入内容（避免回滚）"""
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

    # 探索 ProSeMirror 实例的访问方式
    result = page.evaluate("""() => {
        const el = document.querySelectorAll('.ProseMirror')[1];
        if (!el || !el.pmViewDesc) return {error: 'no pmViewDesc'};
        
        // pmViewDesc 结构探索
        const pm = el.pmViewDesc;
        const info = {
            hasParent: !!pm.parent,
            parentKeys: pm.parent ? Object.keys(pm.parent) : [],
            childrenCount: pm.children ? pm.children.length : 0,
            hasDom: !!pm.dom,
            hasContentDOM: !!pm.contentDOM,
            hasNode: !!pm.node,
            nodeType: pm.node ? pm.node.type.name : null,
            nodeChildCount: pm.node ? pm.node.childCount : null,
            hasDirty: typeof pm.dirty === 'number',
            domIsEditor: pm.dom === el,
            contentDOMParent: pm.contentDOM ? pm.contentDOM.parentNode === el : null
        };
        
        // 尝试找 EditorView：遍历 el 的所有属性
        const elKeys = Object.keys(el).filter(k => !k.startsWith('__'));
        info.elKeys = elKeys;
        
        // 尝试通过 contentDOM 找 view
        if (pm.contentDOM) {
            const cdKeys = Object.keys(pm.contentDOM).filter(k => !k.startsWith('__'));
            info.contentDOMKeys = cdKeys;
        }
        
        return info;
    }""")

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 尝试方法2：通过 window 上的全局变量找 ProSeMirror view
    result2 = page.evaluate("""() => {
        const keys = Object.keys(window).filter(k => {
            try {
                const v = window[k];
                return v && typeof v === 'object' && v.constructor && 
                       (v.constructor.name || '').toLowerCase().includes('prose');
            } catch(e) { return false; }
        });
        return { proseKeys: keys };
    }""")
    print(f"\\nGlobal ProSeMirror keys: {result2['proseKeys']}")

    # 尝试方法3：检查 WeChat 是否暴露了编辑器 API
    result3 = page.evaluate("""() => {
        // 微信编辑器可能挂在 window.WXEditor 或类似对象上
        const candidates = ['WXEditor', 'wxEditor', 'editor', 'weEditor', 'richEditor'];
        const found = {};
        candidates.forEach(k => {
            if (window[k]) found[k] = typeof window[k];
        });
        return found;
    }""")
    print(f"\\nWeChat editor globals: {result3}")
