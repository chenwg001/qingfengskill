# CDP 发布指南（QingFeng-media-ops）

所有平台均为个人账号、无认证，**一律走 CDP 进草稿，绝不点发布**。
**统一使用 Chrome for Testing**（图文+视频全部连它，不用 Edge）。

## 一、统一浏览器：Chrome for Testing

| 项 | 值 |
|---|---|
| 可执行文件 | `D:\chenw\chrome-win64\chrome.exe` |
| Profile | `D:\chenw\chrome-test-profile` |
| CDP 端口 | 9222 |
| 已登录平台 | 公众号、头条、小红书、抖音、快手、B站（全部在这一个 profile） |

### 启动（推荐用保障脚本）

```bash
python {skills_root}/QingFeng-media-ops/scripts/ensure_cft.py
```
- 已运行则跳过；未运行则启动。
- `--check` 只检查不启动。

### 手动启动命令

```powershell
Start-Process "D:\chenw\chrome-win64\chrome.exe" -ArgumentList "--user-data-dir=D:\chenw\chrome-test-profile","--no-first-run","--remote-debugging-port=9222","--remote-allow-origins=*"
```

> 首次使用：在该 Chrome 中手动登录全部六个平台，登录态保存到 profile，后续无需再登。
> 发布器通过 CDP 自动导航到编辑器，无需手动开页面。

## 二、端口与标签页

- 获取已开标签页：`GET http://127.0.0.1:9222/json`
- 每个发布器按 URL 关键词找目标标签页：`douyin.com/creator`、`member.bilibili.com`、`creator.xiaohongshu.com`、`mp.weixin.qq.com`、`mp.toutiao.com`、`cp.kuaishou.com`
- 找不到就新建标签页导航到目标页面。

## 三、各平台进草稿入口（2026-08 实测路径，改版需重查）

| 平台 | 后台入口 | 操作路径 |
|---|---|---|
| 公众号 | mp.weixin.qq.com | 图文消息→新建→填内容→「保存为草稿」 |
| 头条 | mp.toutiao.com | 创作→发文章→填内容→「存草稿」 |
| 小红书 | creator.xiaohongshu.com | 发布笔记→传图/填标题正文→「存为草稿」 |
| 抖音 | creator.douyin.com | 发布视频→上传→填信息→「保存草稿」 |
| 快手 | cp.kuaishou.com | 作品管理→上传视频→填信息→「保存草稿」 |
| B站 | member.bilibili.com | 投稿→上传视频→填标题简介标签→「保存草稿」 |

## 四、表单注入通用技巧（React 页面）

- 文件上传：CDP `DOM.setFileInputFiles` 直接设文件，页面自动触发上传。
- 文本输入：用原生 value setter + 派发 `input`/`change`/`blur` 事件（直接赋值对 React 无效）：
  ```js
  var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(el, '内容');
  el.dispatchEvent(new Event('input', {bubbles:true}));
  el.dispatchEvent(new Event('change', {bubbles:true}));
  ```
- contenteditable 正文区：聚焦后用 `document.execCommand('insertText', false, '文本')` 或直接设置 innerHTML 再触发 input。

## 五、QingFeng-video-publisher 改用 Chrome for Testing

`QingFeng-video-publisher` 原技能默认用 Edge（`browser_edge.py`）。本流水线统一改连 Chrome for Testing：
1. 先 `ensure_cft.py` 启动 CFT（端口 9222）。
2. 不运行 `browser_edge.py`；直接用 CFT 的 CDP 端口 9222 执行 QingFeng-video-publisher 的 upload/fill 脚本（这些脚本接受 `cdp_port` 参数或 tab_id）。
3. 若某脚本硬编码 Edge 路径，临时改为传 `--port 9222` 或在调用前设置环境变量。

## 六、风控与登录态

- 只进草稿不发布，风险最低；每平台每日建议 ≤5 条，节奏模拟真人。
- 遇验证码/滑块/扫码：脚本抛 `NEED_HUMAN` 退出码 42，流水线暂停该平台并通知用户处理一次。
- 登录态失效：重新在 Chrome for Testing 登录后，再跑一次该平台即可（cookie 保存在 profile 中）。
- 平台改版导致选择器失效：修改对应脚本顶部 `SELECTORS` 字典即可，不改逻辑。
