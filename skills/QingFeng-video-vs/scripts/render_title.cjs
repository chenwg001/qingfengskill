#!/usr/bin/env node
// render_title.cjs —— 把 assets/title_effect.html 的 CSS 光效逐帧定格，截成透明 PNG 序列。
//
// 为什么用 PNG 序列而不是 webm/VP9：本机 ffmpeg 编码 yuva420p 后 alpha 会丢，叠加变黑块；
// 透明 PNG 序列（omitBackground）最稳。
//
// 依赖：puppeteer-core（可从 HyperFrames 自带 node_modules 取，或自行 npm i puppeteer-core）
// 浏览器：Playwright Chromium（须带 --use-angle=swiftshader 软件渲染，否则无头截图为黑）
//
// 环境变量（均可选）：
//   CHROME       Chromium 可执行路径
//   TITLE_HTML   HTML 光效文件
//   TITLE_OUT    输出目录（默认当前目录/title_frames）
//   PUPPETEER_CORE  puppeteer-core 模块路径

const path = require('path');
const fs = require('fs');

const candidates = [
  process.env.PUPPETEER_CORE,
  'C:/Users/chenw/AppData/Roaming/npm/node_modules/hyperframes/node_modules/puppeteer-core',
  path.join(__dirname, '..', 'node_modules', 'puppeteer-core'),
];
let puppeteer = null;
for (const c of candidates) {
  if (!c) continue;
  try { puppeteer = require(c); break; } catch (e) { /* try next */ }
}
if (!puppeteer) {
  console.error('[错误] 找不到 puppeteer-core。请 npm i puppeteer-core，或设置 PUPPETEER_CORE 环境变量。');
  process.exit(2);
}

const CHROME = process.env.CHROME ||
  'C:/Users/chenw/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe';
const HTML = process.env.TITLE_HTML ||
  path.join(__dirname, '..', 'assets', 'title_effect.html');
const OUTDIR = process.env.TITLE_OUT || path.join(process.cwd(), 'title_frames');
const FPS = 30;
const SECONDS = 3;            // 一个完整光效循环（呼吸/扫光/光带周期为 3s）
const FRAMES = FPS * SECONDS;

(async () => {
  fs.mkdirSync(OUTDIR, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader',
      '--force-color-profile=srgb',
    ],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1080, height: 540, deviceScaleFactor: 1 });
  await page.goto('file:///' + HTML, { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 200));

  for (let i = 0; i < FRAMES; i++) {
    const t = i / FPS; // 循环内秒数
    await page.evaluate((tsec) => {
      document.getAnimations().forEach((a) => {
        a.pause();
        const dur = a.effect ? a.effect.getTiming().duration : 0;
        if (dur) a.currentTime = (tsec * 1000) % dur;
      });
    }, t);
    const out = path.join(OUTDIR, `f_${String(i).padStart(3, '0')}.png`);
    await page.screenshot({ path: out, omitBackground: true });
  }
  await browser.close();
  console.log('RENDER_DONE frames=' + FRAMES + ' dir=' + OUTDIR);
})().catch(e => { console.error('ERR', e); process.exit(1); });
