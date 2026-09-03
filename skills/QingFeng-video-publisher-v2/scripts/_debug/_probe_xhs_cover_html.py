#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小红书：dump 封面区 HTML，确认是否有隐藏 file input 或上传入口"""
import os, sys, time, json
for _k in ("http_proxy","https_proxy","HTTP_PROXY","HTTPS_PROXY","all_proxy","ALL_PROXY"):
    os.environ.pop(_k, None)
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"

def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)

def main():
    p = sync_playwright().start()
    browser=None
    try:
        browser = p.chromium.connect_over_cdp(CDP)
        page = browser.contexts[0].pages[0]
        log(f"当前页: {page.url}")
        # 找到"设置封面"文本最近的父容器，dump 其内部 HTML（脱敏 src）
        html = page.evaluate("""() => {
            const spans=[...document.querySelectorAll('span,div')].filter(e=>(e.innerText||'').trim()==='设置封面');
            if(!spans.length) return 'NO_SPAN';
            // 向上找包含封面区的容器（找包含设置封面文字且包含 img 的最小祖先）
            let node=spans[0];
            while(node && node!==document.body){
                if(node.querySelectorAll('img').length>=2) break;
                node=node.parentElement;
            }
            if(!node || node===document.body) return 'NO_CONTAINER';
            // 脱敏长 src/data url
            const clone=node.cloneNode(true);
            clone.querySelectorAll('img').forEach(img=>{
                const s=(img.getAttribute('src')||'');
                if(s.length>60) img.setAttribute('src', s.slice(0,60)+'...');
            });
            return clone.outerHTML.slice(0,3000);
        }""")
        log(f"封面区 HTML（前3000字符）:\n{html}")
    except Exception as e:
        log(f"[ERROR] {e}"); import traceback; traceback.print_exc()
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        p.stop()

if __name__ == "__main__":
    main()
