---
name: QingFeng-baijiahao-publisher
description: 将本地 HTML 文件的图文内容自动发布到百家号（baijiahao.baidu.com）。触发词：发布到百家号、发到百家号、百家号。头条号发布请使用 QingFeng-toutiao-publisher，公众号发布请使用 QingFeng-wechat-publisher。
---

# 百家号发布技能

将本地 HTML 文件的图文内容**自动填入**百家号编辑器，用户手动完成最终发布。

**脚本**：`scripts/publish_baijiahao.py`（v12.4，2026-06-30 动态轮询优化）

## 核心规则

- **脚本绝不点击发布按钮** — 最终发布必须由用户手动操作
- **必须使用 Chrome for Testing**（`D:\chenw\chrome-win64\chrome.exe`），CDP 端口 9222，独立 profile：`D:\chenw\chrome-test-profile`
- 启动命令：
  ```bash
  Start-Process "D:\chenw\chrome-win64\chrome.exe" -ArgumentList "--user-data-dir=D:\chenw\chrome-test-profile", "--no-first-run", "--remote-debugging-port=9222", "--remote-allow-origins=*"
  ```
- ⚠️ 不要用 Edge（自动更新导致 UEditor 损坏）或 OpenClaw 隔离浏览器
- **Python 运行环境**：Python314（`C:\Users\chenw\AppData\Local\Programs\Python\Python314\python.exe`），运行脚本用 `python runXX.py` 方式（内嵌路径）

## 前置条件

1. Chrome for Testing 已启动并开启 CDP 端口 9222
2. 已登录百家号后台
3. Python 包：`playwright`、`websocket-client`、`requests`

## 使用方法

当用户说「将某某HTML发布到百家号」时：

1. **读取 HTML 文件**，分析文章标题和正文内容
2. **生成标签**（格式：`#标签名`，空格分隔，至少含 `#教育`）
3. **执行脚本**：

```bash
C:\Users\chenw\AppData\Local\Programs\Python\Python314\python.exe scripts/publish_baijiahao.py "<HTML文件路径>" --tags "#标签1 #标签2" --port 9222
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `html_file` | 要发布的 HTML 文件路径（必填） |
| `--tags` | 话题标签（空格分隔，如 `#教育 #AI`） |
| `--port` | CDP 端口（默认 9222） |

---

## v13 核心教训（2026-07-12）

**批量上传后无需等待图片上传完成，直接点「确认」即可。**

百家号 cheetah-modal 的图片上传是**前端异步处理**，`DOM.setFileInputFiles` 只是把文件加入上传队列。确认按钮点击后，后台上传继续进行，完成后自动将图片插入正文。

**错误做法**：轮询等待所有图片逐张上传完成（40 秒 polling），浪费时间且不稳定。

**正确做法（v13 起）**：
1. `DOM.setFileInputFiles` 设置全部图片路径（数组）
2. 等 **1.5 秒**让弹窗 DOM 稳定
3. 截图看弹窗状态
4. 定位「确认」按钮并点击
5. 等图片出现在正文末尾（动态 polling，最多 20 秒）
6. DOM 重排到正确位置

---

## v12.2 核心方案（已验证 ✅）

### 编辑器结构确认

百家号编辑页面包含两个独立的富文本编辑器：

| 区域 | 编辑器类型 | 标识方式 |
|------|-----------|---------|
| **标题** | Lexical 编辑器 | `.input-box [contenteditable]` 内部 `span[data-lexical-text]` |
| **正文** | UEditor | `UE_V2.instants['ueditorInstant0']` |

⚠️ **关键教训**：`[contenteditable]` 选择器会匹配到 Lexical 标题编辑器而非 UEditor 正文！必须用 UEditor API 操作正文。

### 完整流程（8 步）

#### Step 1 — 检查/导航到编辑器

连接 CDP 端口，找到百家号编辑器页面。若不在编辑页则导航至：
```
https://baijiahao.baidu.com/builder/rc/edit?type=news&is_from_cms=1
```

#### Step 2 — 等待 UEditor 就绪

轮询检测 `UE_V2.instants['ueditorInstant0']` 是否可用，读取初始文本长度。

#### Step 3 — 填写标题（CDP 键盘事件逐字输入）

**Lexical 编辑器会回滚所有 DOM 操作**（innerHTML、textContent、execCommand 均无效）！

唯一有效方案：CDP `Input.dispatchKeyEvent` 带 `text:` 参数逐字输入：

```python
# 1. 聚焦标题框
js_eval(ws, '''(function(){
    var el = document.querySelector('.input-box [contenteditable="true"]');
    if(el) el.focus();
    return !!el;
})()''')

# 2. Ctrl+A 全选（清空旧内容）
cdp_call(ws, 'Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'a', 'code': 'KeyA', 'modifiers': 2})
cdp_call(ws, 'Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'a', 'code': 'KeyA', 'modifiers': 2})

# 3. Delete 删除
cdp_call(ws, 'Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Backspace', 'code': 'Backspace'})
cdp_call(ws, 'Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Backspace', 'code': 'Backspace'})

# 4. 逐字输入标题文本
for char in title:
    cdp_call(ws, 'Input.dispatchKeyEvent', {
        'type': 'char', 'text': char
    })
```

#### Step 4 — 清空 + 注入正文（UEditor API）

```javascript
// 清空
var ed = UE_V2.instants['ueditorInstant0'];
ed.setContent('');
ed.fireEvent('selectionchange');

// 一次性注入完整 HTML（所有段落，不含图片）
ed.execCommand('insertHTML', full_text_html_string);
```

**注意**：
- 必须用 `UE_V2.instants['ueditorInstant0']`，不能用 `[contenteditable]` 选择器
- 一次性注入全部文本 HTML，不用循环逐段插入（避免 selectAll 覆盖前一段）
- 图片不在此步骤处理（见 Step 5）

#### Step 5 — 图片批量上传（一次性弹窗方案）

**核心突破（v12）**：百家号 cheetah-modal 弹窗上传一张后自动关闭且无法重新打开，因此改为一次性批量上传。

```python
# 1. 点击工具栏「插入图片」按钮
cdp_click(ws, '.edui-for-insertimage')

# 2. 等待弹窗出现 → 检测 .cheetah-modal 或 .edui-dialog

# 3. 关闭质量检测弹窗（若有）

# 4. DOM.setFileInputFiles 一次性设置所有图片文件（数组！）
cdp_call(ws, 'DOM.setFileInputFiles', {
    'files': [abs_path_1, abs_path_2, ...],  # 全部图片路径
    'nodeId': file_input_node_id
})

# 5. 等待 20 秒让所有图片上传完成

# 6. 点击一次「确认」按钮（坐标约 (1076, 718)）
mouse_click(ws, confirm_x, confirm_y)

# 7. 所有图片一次性插入正文末尾附近
```

**cover.jpg 特殊处理**：
原 HTML 中 cover.jpg 通常排在最前面（`after_idx=0`），但百家号正文开头不能放图。脚本自动检测并将 cover.jpg 的 `after_idx` 从 0 改为 1（第一段后），其他图片位置不变：

```python
if img_blocks and img_blocks[0][2].lower().startswith('cover'):
    old_idx = img_blocks[0][0]
    img_blocks[0] = (1, img_blocks[0][1], img_blocks[0][2])
    print(f"Cover: moved from after_idx={old_idx} to after_idx=1")
```

#### Step 6.5 — 图片位置 DOM 重排（v12.1 新增）

批量上传的图片全部堆积在正文末尾，需要通过 DOM 操作移动到正确位置。

**不使用 UEditor API**（会触发回滚），直接操作 UEditor body 内部 DOM：

```javascript
var ed = UE_V2.instants['ueditorInstant0'];
var body = ed.body;

// 1. 获取纯文本段落（排除含img的、长度≤2的短段落）
var paras = body.querySelectorAll("p");
var paraList = [];
for (var i = 0; i < paras.length; i++) {
    if (paras[i].querySelector("img")) continue;
    if (paras[i].textContent.trim().length <= 2) continue;
    paraList.push(paras[i]);
}

// 2. 获取所有图片（按DOM顺序）
var imgs = body.querySelectorAll("img");

// 3. 根据 after_idx 映射，cloneNode + insertBefore + removeChild 移动每张图
var targets = [(after_idx, img_name), ...];  // 从 Python 传入
for (var i = 0; i < imgs.length && i < targets.length; i++) {
    var targetParaIdx = targets[i][0] - 1;   // after_idx → paraList 索引
    var targetPara = paraList[targetParaIdx];
    var img = imgs[i];
    
    var wrapper = document.createElement("p");
    wrapper.appendChild(img.cloneNode(true));
    targetPara.parentNode.insertBefore(wrapper, targetPara.nextSibling);
    img.parentNode.removeChild(img);  // 删除原位置
}
```

**运行结果示例**：
```
Upload: success=6, fail=0
Reposition: moved:6/6 paras:33
Body: txtLen=5007, imgCount=6
```

#### Step 7 — 追加话题标签

在正文末尾追加标签文字（如 `#教育 #AI学习 #自适应学习`）。

#### Step 8 — 最终检查 + 截图

- 验证标题文本（无重复）
- 验证正文字数（`ed.getContentTxt().length`）
- 验证图片数量（`<img>` 标签计数）
- 截图保存
- **提示用户手动检查并发布**

---

## 与头条号的关键差异

| 项目 | 头条号 | 百家号 |
|------|--------|--------|
| 编辑器框架 | ProseMirror | UEditor (iframe) + Lexical(标题) |
| 标题操作 | textarea + nativeInputValueSetter | **CDP 键盘事件逐字输入**（Lexical 回滚 DOM） |
| 正文编辑器 | `.ProseMirror` 直接DOM | `UE_V2.instants['ueditorInstant0'].execCommand()` |
| 图片上传 | 逐张 setFileInputFiles | **批量一次性** setFileInputFiles（数组）+ 确认按钮 |
| 图片定位 | 光标定位后插入 | **批量上传后 DOM 重排**（cloneNode+insertBefore+removeChild） |
| 弹窗处理 | ESC | 关闭质量检测弹窗 + 确认按钮点击 |

## 百家号编辑器关键选择器

| 元素 | 选择器 | 备注 |
|------|--------|------|
| 标题框 | `.input-box [contenteditable="true"]` | Lexical 编辑器，只能键盘输入 |
| UEditor 实例 | `UE_V2.instants['ueditorInstant0']` | ⚠️ 不是 UE，不是 instances |
| 图片按钮 | `.edui-for-insertimage` | 需 CDP 鼠标事件点击 |
| 上传弹窗 | `.edui-dialog` 或 `.cheetah-modal` | 只能打开一次！ |
| 确认按钮 | 弹窗内 `button[text*="确认"]` | 通用查找 `button,[role=button],span,div` 过滤 text=`确认`（x>600, y>500），返回数组取第一个 |
| 质量检测弹窗 | 右下角浮层 | 多种选择器尝试关闭 |

## 重要注意事项

1. **Lexical 标题只接受键盘事件** — innerHTML/textContent/execCommand 全部被回滚
2. **正文必须用 UEditor API** — `[contenteditable]` 选的是标题不是正文（v9 的教训）
3. **一次性注入全文** — 循环逐段 insertHTML 会导致后一段覆盖前一段（v8 的教训）
4. **图片只能批量上传** — 弹窗只能打开一次，逐张上传会导致后续 NO_DIALOG（v11→v12 教训）
5. **图片位置用 DOM 重排** — 不依赖 UEditor API，直接 cloneNode+insertBefore+moveChild（v12.1）
6. **cover.jpg 自动修正位置** — `after_idx=0` 自动改为 `1`（正文第一段后）（v12.2）
7. **编码问题** — Windows PowerShell 默认 GBK，脚本开头必须 `sys.stdout.reconfigure(encoding='utf-8')`
8. **Chrome for Testing** — 必须用 Chrome for Testing（CDP 9222），不能用 Edge 或隔离浏览器

## 版本历史

- **v12.2**（2026-06-21）：✅ cover.jpg after_idx 自动修正
**确认按钮选择器修复（v12.2 补充）**：
- 原逻辑：只在弹窗内找 `button[text*="确认"]`，某些环境下找不到
- 新逻辑：通用查找所有 `button, [role=button], .cheetah-btn, span, div`，过滤 text=`确认/确定/插入`，位置过滤 `x>600, y>500`
- 返回数组（非单个），取 `btns[0]`；增加 fallback：直接在 `.cheetah-ui-pro-image-modal-local-upload` 内找 `button`
- 参考：`finish_bjh.py` / `finish_bjh9.py` 已验证有效
（0→1），不再重复上传
- **v12.1**（2026-06-21）：✅ 新增 Step 6.5 DOM 重排，图片从末尾移到正确段落位置（moved:6/6）
- **v12**（2026-06-21）：✅ 批量上传方案（一次弹窗+setFileInputFiles数组+一次确认），解决弹窗无法重复打开问题
- **v11**（2026-06-19）：⚠️ 逐张上传+光标定位方案，单张成功但批量失败（NO_DIALOG）
- **v10**（2026-06-19）：✅ 验证通过基础流程。标题改用 CDP 键盘事件；正文用 UEditor API 一次性注入；图片弹窗上传+确认后验证增量
- **v9**（2026-06-19）：❌ 失败。`[contenteditable]` 匹配到 Lexical 标题编辑器而非正文 UEditor
- **v8**（2026-06-19）：⚠️ 部分成功。文本注入稳定但标题 Lexical DOM 被回滚，图片检测误报
- **v7**（2026-06-19）：❌ 失败。UEditor 过滤 img 占位符，图片全挤末尾
- **v6**（2026-06-19）：✅ 两阶段分离方案首次成功（文本+图片分开处理）
- **v4~v5**（2026-05-17）：早期版本，基于头条号架构改写
