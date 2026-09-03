# script.json 结构规范（QingFeng-video-poem 统一中间表示）

阶段 0 无论输入是「诗名 / 全诗 / 任意叙事文本」，末尾都产出 `<workdir>/script.json`。
阶段 1–5 只读取 `script.json`，不再区分来源——这是本技能泛化支持"任意文本→视频"的关键。

---

## 一、顶层字段（兼容 poem.json，阶段 1–5 直接消费）

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | string | 标题或自拟标题（可选） |
| `author` | string | 作者（古诗填，自由文本可空） |
| `dynasty` | string | 朝代（古诗填，自由文本可空） |
| `lines` | string[] | **逐镜旁白文本**，喂给 `gen_tts.py --lines`，并驱动 `timeline.json` 主时钟 |
| `mood` | enum | BGM 情绪：`nostalgic` / `serene` / `melancholy` / `heroic` / `joyful` |
| `style` | enum | 画风：`ink`(水墨) / `gongbi`(工笔) / `realistic`(写实) / `guofeng`(动画国风) |
| `imagery` | string[] | 整体画面意象关键词 |
| `scene_desc` | string | 整体意境一句话（封面镜用其意象） |
| `n_scenes` | int | 镜头数 = `len(segments) + 1`（含 1 个封面镜） |
| `orientation` | enum | 画面方向：`portrait`(9:16 竖屏，**默认**) / `landscape`(16:9 横屏)。由阶段 0 按用户指令判定，贯穿阶段 1–5：决定首帧尺寸(1024x1536 / 1536x1024) 与成片分辨率(720x1280 / 1280x720) |
| `consistency_brief` | object | **一致性锁**（见下，叙事类重点） |
| `segments` | object[] | **逐镜详情**（见下） |

---

## 二、consistency_brief（跨镜一致性锁，叙事类重点）

古诗因同一诗人、同场景，人设/画风天然连贯；**任意叙事文本动辄多人物多场景，最易"每镜一个人设、画风漂移"**。
因此自由文本必须填 `consistency_brief`，并在阶段 1 把其内容作为**固定前缀**拼进每一张首/尾帧 prompt。

```json
"consistency_brief": {
  "characters": [
    {"name": "阿离", "role": "少女", "appearance": "约十六岁、单马尾、粗布麻衣、眉心朱砂痣"}
  ],
  "style_lock": "工笔画风，暖褐主调，宣纸纹理，细腻线描",
  "setting": "晚唐江南水乡，暮春黄昏，柔光侧逆光"
}
```

- `characters[].appearance`：每个出现人物的**固定外貌描述**，每张涉及该人物的图都原样带入。
- `style_lock`：画风 + 色调 + 质感，所有镜头统一。
- `setting`：时间 / 地点 / 光影锚点，统一场景基调。

> 古诗路径可省略 `characters`（无具体人物），但保留 `style_lock`/`setting` 由 `style`+`imagery` 推导。

---

## 三、segments（逐镜详情）

封面镜用顶层 `scene_desc`；正文每镜对应 `segments` 一项。

```json
"segments": [
  {
    "text": "她提灯穿过回廊，檐角风铃轻响。",
    "mood": "serene",
    "style": "gongbi",
    "imagery": ["灯笼暖光", "木质回廊", "风铃微动"],
    "scene_desc": "少女提灯夜行回廊，风铃轻响。",
    "action_start": "驻足回廊入口，灯未举",
    "action_end": "缓步前行三两步，提灯至胸前，风铃轻晃"
  }
]
```

- `text`：该镜旁白（同时是 `lines` 的对应项）。
- `action_start` / `action_end`：**首尾帧动作差**，须为真实人物姿态变化或物体位移（铁律二），且禁止运镜（铁律三）。
- `mood`/`style`/`imagery`/`scene_desc`：可继承顶层，也可逐镜微调。

---

## 四、自由叙事文本的分镜产出规范（agent 直出 script.json）

1. **理解先行**：先判叙事主线、人物、场景、情绪走向，再决定如何分镜（铁律一）。
2. **切镜**：按**语义断点**切（段落 / 句群 / 场景转换），不要机械按标点；建议 **≤ 8 镜**，`n_scenes = len(segments)+1`。
3. **一致性**：填 `consistency_brief`，角色外貌跨镜原样复用。
4. **动作设计**：每镜 `action_start→action_end` 必有真实动作差（人物姿态 / 物体位移 / 光影流动）。
5. **画风/情绪**：`style` 由文本调性推断（童话→guofeng，纪实→realistic，抒情→ink/gongbi）；`mood` 取整体调性映射到 5 类。
6. **旁白**：默认用原文句子；若要改写画外音，须与原文语义一致。
7. **可视觉化守卫**：纯说明/法条/抽象论述不好画面化时，先向用户确认，或走隐喻/抽象处理，不要硬生成无关画面。

---

## 五、与 poem.json 的关系

- 诗路径：`resolve_poem.py` 输出即本结构（顶层字段齐备，`segments` 可由 agent 在阶段 1 按句细化，`consistency_brief` 由 `style`+`imagery` 推导）。
- 自由文本路径：agent 直接产出本结构，不经诗库。
- 下游（阶段 1–5）只认 `script.json`，故两种来源完全复用同一套视频管线。
