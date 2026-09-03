# 打包 QingFeng-VE 技能包

## 打包命令

```bash
cd D:/chenw/AgentSpace/.agents/skills/QingFeng-VE
zip -r ../QingFeng-VE_skill.zip .
```

## 打包内容

```
QingFeng-VE/
├── SKILL.md              # 技能主文档（含一键配置流程）
├── config_template.md    # 一键配置模板（独立文件，Markdown版本）
├── config_template.docx  # 一键配置模板（Word版本，可打印填写）
└── samples/              # 示例文件
    └── (示例配置和输出)
```

## 使用说明

### 方式一：使用Word模板（推荐）
1. 打开 `config_template.docx`
2. 直接填写或打印后手写
3. 发送填写内容给 AI 助手

### 方式二：使用Markdown模板
1. 打开 `config_template.md`
2. 复制模板内容填写
3. 发送给 AI 助手

### 方式三：直接发送配置
直接发送填写好的配置，无需复制模板

## 交付产物

- 技能包：`QingFeng-VE_skill.zip`
- 模板文件：`config_template.docx`、`config_template.md`
- 成品目录：`output/<项目名称>_完整版.mp4`
