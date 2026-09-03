---
name: QingFeng-toutiao-publisher
description: 将本地 HTML 文件的图文内容自动发布到头条号（mp.toutiao.com）。触发词：发布到头条、发到头条、把文章发到头条、头条号。微信公众号发布请使用 QingFeng-wechat-publisher 技能。
---

## 触发规则（关键）

当用户说「将某某发布到头条」时：
- 识别为**头条号**发布 → 调用 `scripts/publish.py`

当用户说「将某某发布到公众号/微信」时：
- 识别为**微信公众号**发布 → 调用 `scripts/publish_wechat.py`

## 头条号发布（publish.py）✅

> 脚本文件：`scripts/publish.py`

将本地 HTML 文件的图文内容自动填入**头条号**编辑器（mp.toutiao.com）。

**触发词**：头条、头条号、发到头条、把文章发到头条

## 微信公众号发布（publish_wechat.py）✅

> 脚本文件：`scripts/publish_wechat.py`

将本地 HTML 文件的图文内容自动填入**微信公众号**编辑器（mp.weixin.qq.com）。

**触发词**：公众号、微信、发到公众号、发到微信

---

## 微信公众号发布详情

#### 发布到微信公众号

当用户说"将某某HTML发布到微信/公众号"时：

1. **读取 HTML 文件**，分析文章标题和正文内容
2. **执行脚本**（微信不需要话题标签）：

```bash
python scripts/publish_wechat.py "<HTML文件路径>"
```

### 话题标签生成规则（仅头条号需要）

Agent 在执行 publish.py 前，必须根据文章内容生成标签：

1. **必须包含 `#教育`**（教育类文章固定标签）
2. 根据文章标题、小标题、正文关键词生成 3 个相关话题
3. 总共 4 个话题，格式 `#话题名`，空格分隔
4. 话题文字简洁（2-6字）
5. 生成后通过 `--tags` 参数传给脚本

> 如果用户明确指定了标签，则使用用户指定的标签。

---

## 一、头条号发布流程（publish.py）

> 脚本文件：`scripts/publish.py`

### Step 1 — 启动 Chrome for Testing 并导航到编辑器 ✅ 已验证

**关键：使用 Chrome for Testing（不会自动更新），独立 profile 保存登录态**

```powershell
Start-Process "D:\chenw\chrome-win64\chrome.exe" -ArgumentList "--user-data-dir=D:\chenw\chrome-test-profile","--no-first-run","--remote-debugging-port=9222","--remote-allow-origins=*"
```

⚠️ **不要用 Edge**（自动更新会导致编辑器 API 损坏）

**publish.py 已内置自动导航**：连接 CDP 后会检查当前页面 URL，若不在头条编辑器则自动 `Page.navigate` 到 `https://mp.toutiao.com/profile_v4/graphic/publish`，并轮询等待 `.ProseMirror` 编辑器就绪（最多 24 秒）。无需手动导航。

> 如果 Chrome 已在运行且 9222 端口已监听，则跳过启动步骤，直接连接并自动导航。

### Step 2 — 解析 HTML 文件 ✅ 已验证

提取内容块并按原文位置排序：

```python
def parse_html(html_path):
    # 1. 读取 HTML 并预处理 &nbsp;
    html = html.replace('&nbsp;', ' ')
    html = re.sub(r' {2,}', ' ', html)

    # 2. 提取标题 (h1)
    title = 从 <h1> 标签提取

    # 3. 提取所有元素（按类型+位置）
    elements = []
    # h2 → ('title', level=2, text, position)
    # h3 → ('title', level=3, text, position)
    # p   → ('text', text, position)        （排除长度≤5的空段落）
    # div.paragraph → ('text', text, position)  （兼容非标准HTML）
    # img → ('image', abs_path, alt, position)

    # 4. 按原文位置排序（不合并，保持每个原始标签为独立块）
    elements.sort(key=lambda x: x[-1])
    blocks = [e[:-1] for e in elements]

    # 4b. 封面图不单独处理：cover.jpg 作为 HTML 中第一张图，
    #     天然排在最前面，保留在 blocks 中由 Step 3 当作普通图片交叉插入。
    #     （曾经把它 pop 出来用独立 Step 2b 插入空编辑器，弹窗打不开/卡死，已废弃）
    cover_block = None

    return title, blocks, cover_block
```

**关键细节：**
- **&nbsp; 必须在解析阶段预处理**（⚠️ 绝对不能事后操作 ProseMirror 的 innerHTML！会破坏编辑器内部状态）
- 图片路径：相对路径 → 基于 HTML 文件所在目录的绝对路径（不是 images 子目录）
- 排除长度 ≤5 的空段落（避免残留空白标签污染正文）
- **每个原始标签对应一个独立块**：不合并连续段落，保持原文的分段结构
- **block 数据结构**：
  - title: `('title', level(int), text(str))`
  - text: `('text', text(str))`
  - image: `('image', abs_path(str), alt(str))`
- **封面图处理（当前）**：封面 `cover.jpg` 不单独处理，作为 HTML 中第一张图天然排在最前，由 Step 3 当普通图片交叉插入（图片与正文按原序交替上传）。**不要为封面单独开步骤**——独立插入空编辑器时图片弹窗不稳定，会打不开甚至卡死。

### Step 2b — 已移除：封面不再单独处理 ✅ 当前逻辑

封面图（cover.jpg）**不再作为独立步骤**，而是保留在 blocks 中作为第一张图，由 Step 3 的通用图片插入逻辑当作「正文上传过程中的一张普通图片」交叉插入（图片与正文按原序交替上传）。

**为什么移除独立 Step 2b：**
- 独立 Step 2b 在清空编辑器后、正文尚未插入时就把封面当作第一张图插入**空编辑器**，此时图片弹窗按钮不稳定，常打不开（NO_DIALOG），重试/等待逻辑还会卡死整个流程；
- 即便改用以「先插一段文本稳定编辑器」再插封面的思路，也会引入图片重复插入、坐标错位等新问题；
- 正文插图走 Step 3 正常流程一直稳定成功，根因是「编辑器已有内容时按钮稳定」。把封面当作普通图片纳入同一流程即可，无需特殊对待。

> **经验（重要）**：封面就是正文里的一张图，**不要为它单独开步骤**。只要它作为第一张图留在 blocks 中，Step 3 的交替上传自然把它插到正文最前面，且弹窗稳定。

### Step 3 — 填入标题 + 清空编辑器 + 按顺序交替插入正文和图片 ✅ 已验证（v26 核心）

这是最关键的一步。**文字和图片必须按原始 HTML 顺序交替插入**，不能先填完所有文字再追加图片。

#### Step 3a — 填入标题

```javascript
var ta = document.querySelector('textarea');
var setter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, 'value'
).set;
setter.call(ta, "文章标题");
ta.dispatchEvent(new Event('input', {bubbles: true}));
ta.dispatchEvent(new Event('change', {bubbles: true}));
```

#### Step 3b — 清空编辑器

```javascript
var editor = document.querySelector('.ProseMirror');
editor.innerHTML = '<p><br></p>';
```

#### Step 3c/d — 按顺序逐块插入（核心循环）

**文本块：** 通过 `window.__pt` / `window.__plv` 传递参数，用 DOM appendChild 创建元素插入 ProseMirror 编辑器。h2/h3 映射为 `h1.pgc-h-forward-slash`，普通段落为 `<p>`。

**图片块（完整容错流程）：**
```
(a) 光标移到编辑器末尾
(b) ESC 确保无残留 dialog/模式（多次）
(c) scrollTo(0,0) + 重新获取图片按钮坐标 + scrollIntoView
(d) mouse_click 点击图片按钮 → 等4s
(e) DOM.querySelectorAll 查找 input[type=file]
(f) setFileInputFiles 设置文件路径 → 等5s
(g) 检查 img 数量：
     ├─ 增加了 → 成功 ✓
     └─ 未增 → 点「确定」→ 等5s → 再检查:
          ├─ 增加了 → 成功 ✓
          └─仍未增 → 失败 ✗
(h) ESC 退出图片描述模式
```

**重试逻辑（对话框未弹出时）：**
- 最多重试 3 次
- 每次：ESC×3 → scrollTo(0,0) → 重新获取坐标 → mouse_click → 等4s → 再查 input

### Step 4 — 在文章末尾添加话题标签 ✅

所有正文和图片插入完成后，在编辑器末尾追加一个段落包含4个话题标签。

### Step 5 — 最终检查 + 截图 + 提示用户手动发布 ✅

验证标题字数、正文字数、图片数量、话题标签，截图保存，提示用户手动发布。

---

## 二、微信公众号发布流程（publish_wechat.py）✅ v3 已验证成功

> 脚本文件：`scripts/publish_wechat.py`

### 整体策略（v3 验证成功的完整流程）

与头条号完全不同的策略——微信使用 **ProseMirror 编辑器**，直接 DOM 修改会被回滚，
因此采用 **「先上传收集 CDN URL → 构建完整 HTML → execCommand 一次性注入」** 的方案。

### 微信编辑器特点（已验证）

| 特性 | 头条号 | 微信公众号 |
|------|--------|-----------|
| 编辑器框架 | ProseMirror | **ProseMirror（新版）** |
| 标题选择器 | `textarea[placeholder="请输入文章标题"]` | **`#title`（TEXTAREA）** |
| 作者选择器 | 无 | **`#author`（INPUT）** |
| 正文编辑器 | `.ProseMirror`（单个） | **`.ProseMirror[1]`（第二个，index=1 是正文）** |
| 正文内标题 | 无单独字段 | **`.ProseMirror[0]`（第一个，index=0 是标题编辑器）** |
| 图片按钮 | `.syl-toolbar-tool.image` | **`#js_editor_insertimage`** |
| 图片上传方式 | mouse_click + setFileInputFiles | **`input[type=file].set_input_files()` 直接设置** |
| 封面图 | 自动取首张 | **需单独上传** |
| 模板选择 | 无 | **需先选主模板** |

### 发布步骤（完整已验证流程）

#### Step 0 — 前置准备：连接 CDP + 解析 HTML

```
1. connect_over_cdp('http://localhost:9222') 连接已有 Edge
2. parse_html(html_file) 解析 HTML：
   - 提取 <h1> 作为标题
   - 提取所有 <p>/<div.paragraph> 作为正文段落
   - 提取所有 <img src="..."> 作为配图（路径基于 HTML 文件所在目录）
   - 排除长度≤5 的空段落
```

**⚠️ 图片路径规则（重要）：**
- 图片文件在 **HTML 文件同目录下**，不是统一的图片子目录
- 例如：`D:\办公\宿松县教育局\个人\随笔\从科学教育到科技教育\index.html`
- 配图在同目录：`...\从科学教育到科技教育\illustration_1.jpg` ~ `illustration_N.jpg`
- 封面图：`cover.jpg` 或用文章第一张配图

#### Step 1 — 选择模板 ✅ 已验证

进入编辑器页面后，**第一步是选择「主模板」**：

```javascript
// 找到并点击模板区域中的「主模板」选项
// 主模板通常是默认/基础模板，选择后在编辑区显示模板结构
// 模板第一张图片下方有正文填充区域
```

> ⚠️ 必须先选模板再填内容，否则编辑器结构不正确。

#### Step 2 — 上传所有图片，收集 CDN URL ✅ 已验证（核心突破）

这是整个流程的关键创新点。**先不上传就注入 HTML 的话，图片只会显示为 16×16 占位符。**

```python
for each image_file in article_images:
    # 2a. 记录当前编辑器中已有的 mmbiz 图片数量
    before_count = count_mmbiz_images()

    # 2b. 通过 file input 直接设置文件（不需要点击按钮！）
    file_inputs = page.query_selector_all('input[type="file"]')
    for fi in file_inputs:
        fi.set_input_files(image_path)  # Playwright API
        break

    # 2c. 等待上传完成（大图 >300KB 需要 4 秒）
    time.sleep(4)

    # 2d. 检测新增的 mmbiz.qpic.cn 图片，提取 CDN URL
    new_images = get_new_mmbiz_images(before_count)
    if new_images:
        cdn_urls[image_file] = new_images[-1]['src']  # 取最后一张（刚上传的）
    else:
        time.sleep(3)  # 再等一次
        retry = get_new_mmbiz_images(before_count)
        if retry:
            cdn_urls[image_file] = retry[-1]['src']
```

**关键细节：**
- 微信编辑器的 file input 可以直接 `set_input_files()`，**不需要先点击图片按钮展开菜单**
- 上传成功后微信会将图片以 `<SECTION>` 包裹追加到编辑器末尾
- 通过对比上传前后的 mmbiz 图片数量来识别新上传的图片
- CDN URL 格式：`https://mmbiz.qpic.cn/mmbiz_jpg/vephia81ehl...` 或 `mmbiz_png/...`
- 图片尺寸通常为 1280×719（自然尺寸），编辑器中显示可能缩放

#### Step 3 — 构建完整 HTML 并一次性注入 ✅ 已验证

**用 execCommand 绕过 ProseMirror 的 DOM 回滚机制：**

```javascript
// 3a. 保存当前编辑器原始 HTML（包含占位符 img）
const original_html = editorEl.innerHTML;

// 3b. 将占位符 src 替换为真实 CDN URL（正则替换）
//     illustration_1.jpg → https://mmbiz.qpic.cn/mmbiz_jpg/...
//     同时修复 width="16" height="16" → style="width:100%;height:auto;display:block;"

// 3c. 全选 → 删除 → 注入新HTML（三步走，绕过 ProseMirror 回滚）
editorEl.focus();
document.execCommand('selectAll', false, null);
document.execCommand('delete', false, null);
document.execCommand('insertHTML', false, newHTML);  // ← 关键！execCommand 注入不会被回滚
```

**为什么这个方法有效：**
- ❌ 直接修改 `img.src` → 被 ProseMirror 状态管理器**回滚**
- ❌ 直接赋值 `editorEl.innerHTML` → 破坏 ProseMirror 内部状态
- ✅ `execCommand('insertHTML')` → **ProseMirror 会正常接受并通过事务系统处理**

#### Step 4 — 填写各处标题 ✅ 已验证

微信编辑器有 **三个地方需要填标题**：

```javascript
// 4a. 左侧标题栏（#title，TEXTAREA）
const titleInput = document.querySelector('#title');
const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
setter.call(titleInput, articleTitle);
titleInput.dispatchEvent(new Event('input', { bubbles: true }));
titleInput.dispatchEvent(new Event('change', { bubbles: true }));

// 4b. 正文上方的标题（.ProseMirror[0]，第一个 ProseMirror 是标题编辑器）
const titleEditor = document.querySelectorAll('.ProseMirror')[0];
titleEditor.focus();
document.execCommand('selectAll', false, null);
document.execCommand('insertText', false, articleTitle);

// 4c. 作者（#author，INPUT）
const authorInput = document.querySelector('#author');
const authorSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
authorSetter.call(authorInput, authorName);
authorInput.dispatchEvent(new Event('input', { bubbles: true }));
authorInput.dispatchEvent(new Event('change', { bubbles: true }));
```

#### Step 5 — 上传封面图 ✅ 已验证

```python
# 用文章第一张配图作为封面
cover_path = os.path.join(article_dir, "illustration_1.jpg")
# 或目录下的 cover.jpg

# 封面图通过页面上的封面上传按钮 / file input 上传
# 与正文图片上传方式相同：set_input_files()
```

#### Step 6 — 最终验证 + 截图 + 提示用户 ✅ 已验证

```javascript
final_check = {
    title: document.querySelector('#title')?.value,
    author: document.querySelector('#author')?.value,
    bodyTitle: document.querySelectorAll('.ProseMirror')[0]?.textContent,
    textLength: document.querySelectorAll('.ProseMirror')[1]?.textContent.length,
    images: Array.from(document.querySelectorAll('.ProseMirror')[1].querySelectorAll('img')).map(img => ({
        src: img.src.substring(0, 80),
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight
    }))
}
```

验证项：
- 左侧标题 = 文章标题 ✓
- 正文上方标题 = 文章标题 ✓
- 作者 = 正确 ✓
- 正文字数 > 0 ✓
- 所有图片 naturalWidth > 100（不是 16×16 占位符）✓
- 截图保存 → 提示用户手动检查和发布

---

## 三、技术要点（踩坑记录）

### 为什么用这些方法？

| 问题 | 错误做法 | 正确做法 |
|------|---------|---------|
| 标题不生效 | `textarea.value = 'xxx'` | `nativeInputValueSetter.call(ta, val)` + input/change事件 |
| 正文被截断(30字) | `document.execCommand('insertText')` | DOM `appendChild` 创建 p 元素 + textNode |
| base64 格式化报错 | `%r` 直接格式化 base64 字符串 | 先存 `window.__变量` 再读取 |
| 标题重复在正文 | 直接提取 body 全部内容 | 正则排除 h1/h2 后再解析 |
| **图片全部堆末尾** | 先填完所有文字再批量上传图片 | **文字和图片按原序交替插入** |
| **后续图传不上** | 上传后不处理编辑器状态 | **每次上传后按ESC退出图片描述模式** |
| **ProseMirror 内容丢失** | 对已填充内容的编辑器做 innerHTML 替换 | 只在清空时用innerHTML，之后只用 appendChild |
| **JS click 不触发对话框** | `element.click()` 通过 CDP | **mouse_click 坐标点击**（需真实用户手势） |
| **按钮坐标偏移** | 只获取一次坐标固定使用 | **每次上传前重新 getBoundingClientRect** |
| **Windows GBK编码报错** | print/log 中包含 emoji 字符 | 移除所有 emoji，用纯 ASCII 标记 |
| **微信图片显示16x16** | 先注入带占位符HTML再尝试替换img.src | **先上传拿CDN URL → execCommand('insertHTML')一次性注入** |
| **微信DOM修改被回滚** | 直接修改 img.src 或 innerHTML | **execCommand('selectAll+delete+insertHTML')绕过ProseMirror** |

### 微信编辑器 DOM 结构（已验证）

```
textarea#title                              ← 左侧标题输入框
input#author                                ← 作者输入框
div.ProseMirror [index=0]                   ← 正文上方标题编辑器（也需要填！）
div.ProseMirror [index=1]                   ← 正文富文本编辑器（主编辑区）
  ├─ section                               ← 微信包裹的图片容器
  │   └─ img[src="mmbiz.qpic.cn/..."]      ← 上传后的真实图片
  ├─ span                                  ← 占位符包裹（illustration_N.jpg, 16×16）
  │   └─ img[src="...illustration_N.jpg"]  ← 占位符图片
  └─ p / h2 / h3 / div                     ← 文本内容
button#js_editor_insertimage                ← 工具栏图片按钮
input[type=file][accept=image/*]            ← 文件上传输入框（可直接set_input_files）
```

### 微信全局 JS 变量（探测结果）

| 变量 | 类型 | 说明 |
|------|------|------|
| `$EDITORUI` | Object | 微信编辑器 UI 框架 |
| `__MpEditor` | Function | 编辑器构造函数 |
| `__MP_Editor_JSAPI__` | Object | 有 `invoke`/`on` 方法，JSAPI 桥接 |
| `__mpTitleEditor` | Vue实例 | 标题编辑器的 Vue 实例 |
| `editorEl.pmViewDesc` | ViewDesc | ProseMirror 视图描述符（nodeType='doc'，parent=undefined） |

### 图片上传方式对比

| 方式 | 头条号 | 微信公众号 |
|------|--------|-----------|
| **触发方式** | mouse_click 坐标点击图片按钮 | **直接 `set_input_files()` 设置 file input** |
| **等待时间** | 点击后等4s | 设置后等4s（大图）+ retry 3s |
| **确认方式** | 检查编辑器 img 数量增加 | **检测新增 `mmbiz.qpic.cn` 图片** |
| **URL获取** | 编辑器内部自动处理 | **从 DOM 中提取新出现的 mmbiz img src** |
| **重试** | ESC ×3 → 重选坐标 → 重试 | **多等 3 秒再检测一次** |

### Edge 远程调试注意事项

⚠️ **必须加 `--remote-allow-origins=*` 参数**，否则 CDP WebSocket 连接会返回 404

⚠️ **CDP 端口**：9222（browser_edge.py 动态分配，不再固定使用 28800）

## HTML 文件要求

- 标准 HTML 文件，包含 `<body>` 内容
- 标题使用 `<h1>` 或 `<h2>` / `<h3>` 标签
- 正文使用 `<p>` 标签或 `<div class="paragraph">`
- 图片使用 `<img src="相对路径">` 标签
- **图片文件与 HTML 在同一目录**（微信公众号）
- 封面图为 `cover.jpg` 或使用文章第一张配图

## 依赖

```bash
pip install websocket-client playwright
```

无需 BeautifulSoup 等其他库（使用正则解析，更轻量）。

## 版本历史

| 版本 | 平台 | 状态 | 说明 |
|------|------|------|------|
| v20 | 头条 | ✅ | 第二篇文章成功（base64内联方案） |
| v21-v23b | 头条 | ✅ | 第三篇探索期（发现 setFileInputFiles 方案） |
| v24 | 头条 | ❌ | innerHTML 破坏 ProseMirror 事故 |
| v25 | 头条 | ⏭️ | skill 重写版（未完整测试） |
| step3 | 头条 | ⏭️ | 分步验证版（有4个bug） |
| step3_fixed | 头条 | ⚠️ | 修bug但图片只成功1/6（未ESC退出模式） |
| **v26** | **头条** | **✅ 最终版** | **文字+图片按原序交替插入 + 每次上传后ESC + 完全成功** |
| **v27** | **头条** | **✅ 历史版** | **v26 + 末尾话题标签(#格式) + 绝不点击发布 + 连续段落合并优化** |
| **v29** | **头条** | **✅ 历史版** | **v26 + 移除段落合并逻辑，保持原文分段结构** |
| **v30** | **头条** | **✅ 历史版** | **封面图 cover.jpg 优先插入正文最前面，专属5次重试+3秒初始化等待** |
| **v31** | **头条** | **✅ 历史版** | **v30 + 点击后等8秒（从5秒→8秒）+ 重试前重新获取按钮坐标** |
| **v32** | **头条** | 历史版 | v31 + Step2b改为与Step3正文图一致逻辑（按钮就绪检测+NO_DIALOG重试3次） |
| **v33** | **头条** | **历史版** | **v32 + `mouse_click` 新增 `mouseMoved` 前置事件（核心根因修复：模拟真实鼠标移动触发 hover，否则按钮点击处理器未挂载导致点击落空）。JS `element.click()` 兜底已移除（非受信事件打不开弹窗）。实测清空编辑器后立即点击 3/3 成功** |
| **v34** | **头条** | **✅ 当前版** | **移除 Step 2b 独立封面步骤：封面作为普通图片纳入 Step 3 交替上传（图片与正文交叉插入），不再单独开步骤。修复多个 file input 导致的重复上传（只取第一个 input）。封面稳定插入正文最前** |
| **v28** | **微信** | **❌ 初版** | **基于UEditor假设编写，实际微信已改用ProseMirror** |
| **v3** | **微信** | **✅ 验证成功** | **先上传收集CDN URL → execCommand注入 → 5/5图片成功** |
