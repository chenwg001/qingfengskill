# Video Publisher - 完整操作流程文档

## ⚡ 核心上传方法（2026-04-11 更新）

### 文件上传原理

**`DOM.setFileInputFiles` 本身就能触发上传，不需要 React onChange！**

- `DOM.setFileInputFiles` 设置 `input.files`（返回 `{}` = 成功）
- 设置后页面**自动跳转**到发布页 `/content/post/video`
- 发布页有 2 个 file input（视频 + 封面），`filesLength` 清零（已触发上传）
- 发布页直接显示视频 blob 预览 + 封面 blob 预览

### 关键参数

| 参数 | 值 | 说明 |
|------|---|------|
| CDP 端口 | **9222**（browser_edge.py 动态分配）| Edge 浏览器调试端口 |
| WebSocket URL | `ws://127.0.0.1:{port}/devtools/page/{tab_id}` | 直接连接到页面 |
| 上传方法 | `DOM.setFileInputFiles` | CDP 命令 |
| 成功标志 | 返回空对象 `{}` | 表示上传命令执行成功 |

### 上传脚本

**位置**：`C:\Users\chenw\.qclaw\skills\QingFeng-video-publisher\scripts\upload_video.py`

---

## 📋 完整操作流程（抖音发布为例）

### 场景
用户要求：将"AI育见"文件夹中"4.1"文件夹内的视频发布到抖音

---

#### Step 1: 确认文件夹位置和内容

```powershell
Get-ChildItem -Path "D:\个人\资源\个人文章\AI育见\4.1" | Select-Object Name, Length
```

**确认文件**：
- 视频文件：`4.1.mp4`
- 封面图片：`4.1-封面.jpg` 或 `4.1-封面.png`

---

#### Step 2: 生成封面副本

```bash
python "C:\Users\chenw\.qclaw\skills\QingFeng-video-publisher\scripts\create_cover_copies.py" "D:\个人\资源\个人文章\AI育见\4.1"
```

**生成的文件**：
| 文件 | 尺寸 | 比例 | 用途 |
|------|------|------|------|
| 4.1-封面_4x3.jpg | 2880×2160 | 4:3 | 横封面 |
| 4.1-封面_3x4.jpg | 2880×3840 | 3:4 | 竖封面 |

**处理规则**：
- ✅ 通过缩放调整比例（纯缩放，非裁剪）
- ✅ 不加黑边、不裁剪
- ✅ 使用 LANCZOS 高质量缩放

---

#### Step 3: 启动浏览器

```bash
python "C:\Users\chenw\.qclaw\skills\QingFeng-video-publisher\scripts\browser_edge.py"
```

**预期输出**：
```
[INFO] 启动 Edge，CDP 端口: 9222
[INFO] Edge PID: 12345
[抖音标签] xxxxx | 抖音创作者中心 | https://creator.douyin.com/creator-micro/home

[RESULT]
CDP_PORT=9222
CREATOR_TAB=xxxxxxxx
```

**⚠️ 重要：必须使用用户真实 Edge profile（含登录态），不要用 `browser --action start` 的隔离浏览器**

---

#### Step 4: 导航到发布页

**正确方式：首页 → 点击「高清发布」→ 等待跳转**

❌ 错误：直接导航到 `creator.douyin.com/creator-micro/content/post/video`
✅ 正确：从首页点击按钮（触发 SPA 路由跳转）

```python
# Python - 导航 + 点击「高清发布」
# 见 browser_edge.py 脚本中的导航逻辑
```

---

#### Step 5: 上传视频

**点击「上传视频」按钮后执行：**

```bash
python "C:\Users\chenw\.qclaw\skills\QingFeng-video-publisher\scripts\upload_video.py" \
  "<tab_id>" \
  "D:\个人\资源\个人文章\AI育见\4.1\4.1.mp4"
```

**预期输出**：
```
[Step1] file input nodeId: 780
[Step2] setFileInputFiles: {}
[OK] setFileInputFiles 成功，页面将自动跳转
```

**上传后页面自动跳转到** `https://creator.douyin.com/creator-micro/content/post/video`

---

#### Step 6: 等待视频处理

**等待时间**：300-500MB 视频约需 1-2 分钟

**验证方式**：
- URL 变为 `/content/post/video`
- blob 预览图出现（IMG src 含 `blob:`）
- 页面显示封面选项（4:3 / 3:4）

---

#### Step 7: 封面设置（⚠️ 待验证）

发布页显示：
- 「4:3」和「3:4」封面选项 + 「AI推荐封面」
- 可能需要上传自定义封面？
- 封面上传流程待验证

**待确认：封面上传是否在发布页直接操作，还是需要打开封面设置对话框？**

---

#### Step 8: 填写标题和简介

**标题示例**：
```
AI育见4.1：个性化学习路径规划全攻略
```

**简介示例**：
```
探索AI如何为每个孩子规划专属的学习路径，让教育真正实现"因材施教"。通过智能诊断、动态调整和精准推送，AI技术让个性化学习从理想变为现实。

#教育 #AI教育 #个性化学习 #教育科技 #智慧教育
```

---

#### Step 9: 添加 AI 声明

1. 找到"发文助手"区域
2. 点击"添加声明"
3. 选择"内容由AI生成"
4. 点击"确定"

---

#### Step 10: 停止并提示用户手动发布

**完成所有准备工作后**：
- ✅ 视频已上传
- ✅ 封面已设置
- ✅ 标题已填写
- ✅ 简介已填写（含话题）
- ✅ AI声明已添加

**停止操作，提示用户**：
```
✅ 抖音发布信息已填写完毕，请检查后手动点击发布按钮。
```

---

## 🔑 关键要点总结

### 1. CDP 连接参数

| 参数 | 值 | 说明 |
|------|---|------|
| CDP 端口 | 9222（动态）| browser_edge.py 分配 |
| WebSocket | `ws://127.0.0.1:{port}/devtools/page/{id}` | 页面 WebSocket URL |
| 上传方法 | `DOM.setFileInputFiles` | **不需要 React onChange** |

### 2. 上传验证方式

| 验证点 | 方法 |
|--------|------|
| setFileInputFiles 成功 | 返回 `{}` |
| 页面跳转 | URL 变为 `/content/post/video` |
| 视频上传完成 | blob 预览图出现 |
| 封面 | 4:3/3:4 选项显示 |

### 3. 封面处理规则

| 比例 | 处理方式 | 示例尺寸 |
|------|---------|---------|
| 4:3 横版 | 高度不变，缩放宽度 | 2880×2160 |
| 3:4 竖版 | 宽度不变，缩放高度 | 2880×3840 |

### 4. 发布流程

| 步骤 | 操作 | 是否自动 |
|------|------|---------|
| 生成封面副本 | 缩放图片 | ✅ 自动 |
| 上传视频 | CDP setFileInputFiles | ✅ 自动 |
| 设置封面 | 待验证 | 待验证 |
| 填写标题简介 | 输入文本 | ✅ 自动 |
| 添加AI声明 | 选择声明 | ✅ 自动 |
| **点击发布** | 发布视频 | ❌ **手动** |

---

## ⚠️ 常见问题排查

### Q1: WebSocket 连接失败

**错误信息**：`ConnectionRefusedError` / `websockets.exceptions`

**解决方案**：
1. 检查 Edge 浏览器是否正在运行
2. 检查 CDP 端口是否正确
3. 重新运行 `browser_edge.py`

### Q2: 上传后页面无变化

**可能原因**：
1. file input nodeId 过期（页面刷新后需重新获取）
2. 文件路径错误
3. 上传到错误的 file input

**解决方案**：
```python
# 重新获取所有 file input
r = await cdp("DOM.querySelectorAll", {
    "selector": "input[type=file]",
    "nodeId": body_id
})
node_ids = r.get("result", {}).get("nodeIds", [])
```

### Q3: setFileInputFiles 返回非空

**可能原因**：文件路径格式问题

**解决方案**：确认文件路径是绝对路径，且文件存在

---

## 📁 相关文件

| 文件 | 用途 |
|------|------|
| `SKILL.md` | 技能说明文档 |
| `WORKFLOW.md` | 操作流程文档（本文件） |
| `scripts/upload_video.py` | 视频上传脚本（已验证） |
| `scripts/browser_edge.py` | 浏览器启动脚本（已验证） |
| `scripts/create_cover_copies.py` | 封面生成脚本 |

---

**最后更新**：2026-04-11
**更新内容**：
- **抖音视频上传不需要 React onChange**，`DOM.setFileInputFiles` 本身就能触发上传
- CDP 端口改为 9222（browser_edge.py 动态分配）
- 上传后页面自动跳转，`setFileInputFiles` 返回 `{}` 即成功
- 浏览器改用用户真实 Edge profile
