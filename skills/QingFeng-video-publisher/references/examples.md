# 视频发布技能 - 使用示例

本文档提供 `QingFeng-video-publisher` 技能的实际使用案例。

## 示例 1：发布单个视频到抖音（使用配置文件）

### 步骤 1：准备配置文件

创建 `publish_config.json`：

```json
{
  "video_path": "D:/个人/资源/个人文章/AI育见/5.1/5.1.mp4",
  "title": "AI+跨学科融合：4.4 挑战与反思",
  "description": "探讨AI与跨学科融合的挑战与边界，分享实践经验与反思。",
  "tags": ["AI教育", "跨学科", "教学反思"],
  "ai_declaration": "视频由AI生成",
  "platform": "douyin",
  "cover_source": "D:/个人/资源/个人文章/AI育见/5.1/封面.jpg",
  "output_dir": "D:/个人/资源/个人文章/AI育见/5.1/"
}
```

### 步骤 2：运行发布脚本

```bash
python C:/Users/chenw/.workbuddy/skills/QingFeng-video-publisher/scripts/publish_video.py --config publish_config.json
```

### 预期结果

1. 脚本自动检测封面是否存在，不存在则生成
2. 启动本地 Edge 浏览器（可视化界面）
3. 打开抖音创作者中心
4. 如需登录，等待用户手动登录
5. 自动上传视频（无50MB限制）
6. 自动上传横屏 (4:3) 和竖屏 (3:4) 封面
7. 自动填写标题、简介、AI声明
8. 保持浏览器打开，等待用户确认后手动点击「发布」

---

## 示例 2：使用命令行参数（快速发布）

```bash
python C:/Users/chenw/.workbuddy/skills/QingFeng-video-publisher/scripts/publish_video.py \
  --video "D:/个人/资源/个人文章/AI育见/5.1/5.1.mp4" \
  --platform douyin \
  --title "AI+跨学科融合：4.4 挑战与反思" \
  --description "探讨AI与跨学科融合的挑战与边界" \
  --cover-source "D:/个人/资源/个人文章/AI育见/5.1/封面.jpg" \
  --ai-declaration "视频由AI生成"
```

---

## 示例 3：只生成封面（不发布）

```bash
python C:/Users/chenw/.workbuddy/skills/QingFeng-video-publisher/scripts/make_cover.py \
  --source "D:/个人/资源/个人文章/AI育见/5.1/封面.jpg" \
  --output-dir "D:/个人/资源/个人文章/AI育见/5.1/"
```

生成文件：
- `封面_cover_4x3.jpg` (横屏 4:3)
- `封面_cover_3x4.jpg` (竖屏 3:4)

---

## 示例 4：批量发布多个视频

创建批量配置文件 `batch_publish.json`：

```json
{
  "videos": [
    {
      "video_path": "D:/个人/资源/个人文章/AI育见/5.1/5.1.mp4",
      "title": "第5.1集",
      "platform": "douyin"
    },
    {
      "video_path": "D:/个人/资源/个人文章/AI育见/5.2/5.2.mp4",
      "title": "第5.2集",
      "platform": "douyin"
    }
  ]
}
```

使用批量发布脚本（需额外创建 `scripts/batch_publish.py`）：

```bash
python C:/Users/chenw/.workbuddy/skills/QingFeng-video-publisher/scripts/batch_publish.py --config batch_publish.json
```

---

## 常见问题

### Q1：脚本找不到浏览器？

**A**：确保已安装 Chrome 或 Edge 浏览器。脚本会自动检测以下路径：
- `C:\Program Files\Google\Chrome\Application\chrome.exe`
- `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
- `C:\Program Files\Microsoft\Edge\Application\msedge.exe`
- `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`

### Q2：视频上传失败？

**A**：
1. 检查视频文件是否存在
2. 确保浏览器已登录对应平台
3. 检查网络连接
4. 查看浏览器控制台错误信息

### Q3：封面生成失败？

**A**：
1. 确保已安装 Pillow 库：`pip install Pillow`
2. 检查源图片路径是否正确
3. 确保输出目录存在且有写入权限

### Q4：如何发布到快手或百家号？

**A**：目前仅抖音平台完全支持。快手和百家号的支持正在开发中。

修改配置文件中的 `"platform"` 字段为 `"kuaishou"` 或 `"baijiahao"` 即可，但功能可能不完整。

---

## 技能优势

相比之前的一次性脚本，此技能具有以下优势：

1. **通用性**：不依赖特定文件名，可用于任意视频
2. **可配置**：通过 JSON 配置文件或命令行参数指定所有参数
3. **多平台支持**：框架支持多个平台，易于扩展
4. **可视化操作**：启动本地浏览器，可看到完整操作过程
5. **自动处理**：自动生成封面、处理弹窗、填写表单
6. **可复用**：作为技能保存，可被任意视频发布任务复用

---

**下一步**：测试此技能，确保其正常工作，然后根据反馈迭代改进。
