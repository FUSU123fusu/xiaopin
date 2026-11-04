# 小品工厂（xiaopin）设计文档

日期：2026-11-04
状态：已批准，进入实现

## 1. 目标

把一篇 PDF / Word / 网页 / Markdown / 纯文本，改写成一出多角色喜剧小品，并自动配音，产出完整音频、字幕、可读剧本和分角色音轨。

## 2. 形态

Claude Code Skill + Python 脚本流水线。调用方式：

- 斜杠命令：`/xiaopin <路径或URL> [--style 相声] [--roles 3] [--engine edge]`
- 自然语言："把这篇做成小品" / "做成相声" / "把这篇论文改成双人小品"

## 3. 架构

```
D:\Projects\xiaopin\
├── SKILL.md                  # 触发词、流程编排、风格路由
├── README.md
├── requirements.txt
├── config.example.json       # TTS 渠道配置模板
├── scripts/
│   ├── extract.py            # 输入 → 纯文本
│   ├── tts.py                # script.json → 逐句音频 + manifest.json
│   ├── assemble.py           # manifest → mp3/srt/md/tracks
│   └── engines/
│       ├── __init__.py       # load_engine(name)
│       ├── edge.py           # 默认，零配置
│       ├── openai.py         # 需 API Key
│       └── local.py          # 调本地 HTTP 服务（CosyVoice 等）
├── references/
│   ├── styles.md             # 四种风格写法 + 音色对照表
│   └── script-schema.md      # 剧本 JSON 契约
└── tests/
```

**职责切分**：脚本只做确定性工作（抽文本、合成、拼装）。唯一的智能环节——把文章改写成小品——由 Claude 完成。因此中间产物是 JSON，不是自然语言。

## 4. 数据流

```
文件/链接
   │ extract.py  → {"title","source","text","char_count"}
   ▼
纯文本
   │ Claude 生成（读 styles.md 选风格、定角色、写台词）
   ▼
script.json  ← 唯一中间契约
   │ tts.py（可插拔引擎）
   ▼
audio/line_0001.mp3 … + manifest.json（每句时长、起始偏移）
   │ assemble.py
   ▼
out/<slug>.mp3      完整音频
out/<slug>.srt      字幕
out/<slug>.md       可读剧本
out/tracks/*.mp3    分角色音轨
```

## 5. 剧本契约（script.json）

```json
{
  "title": "…",
  "style": "comedy | xiangsheng | talk | edu",
  "source": {"file": "…", "char_count": 3200},
  "characters": [
    {"id": "A", "name": "老张", "persona": "轴，认死理",
     "voice": "zh-CN-liaoning-XiaobeiNeural", "rate": "-5%", "pitch": "+0Hz"}
  ],
  "lines": [
    {"speaker": "A", "text": "…", "emotion": "急", "pause_after_ms": 600}
  ]
}
```

约束：`speaker` 必须是 characters 中的 id；单句不超过 40 字（保证字幕可读）；角色数默认 2，可指定 N。

## 6. TTS 可插拔

统一接口：

```python
def synthesize(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> None
```

`config.json` 的 `engine` 字段决定加载哪个模块（edge / openai / local），剧本逻辑不变。默认 edge-tts：无需 key、无需显卡。

音色是喜剧效果的关键。edge-tts 自带方言音色：

| 音色 | 特点 |
|---|---|
| `zh-CN-liaoning-XiaobeiNeural` | 东北话女声，Humorous |
| `zh-CN-shaanxi-XiaoniNeural` | 陕西话女声，Bright |
| `zh-CN-YunxiNeural` | 男声，活泼 |
| `zh-CN-XiaoxiaoNeural` | 女声，温暖 |
| `zh-CN-YunjianNeural` | 男声，激情 |
| `zh-CN-YunyangNeural` | 男声，专业稳重（适合旁白/科普） |

喜剧小品主角默认配东北话。

## 7. 风格与时长

四种风格各有一份结构模板（见 references/styles.md）：
- **喜剧小品**：场景冲突 → 误会升级 → 反转 → 升华收尾
- **双人相声**：一捧一逗、三翻四抖、现挂
- **播客对谈**：真实分歧、口语、举例子
- **知识科普**：类比 + 问答节奏

时长自动适配（中文 TTS ≈ 4.5 字/秒）：

| 原文长度 | 成片时长 | 台词目标 |
|---|---|---|
| < 2000 字 | 3–5 分钟 | 800–1200 字 |
| 2000–8000 字 | 6–9 分钟 | 1500–2400 字 |
| > 8000 字 | 10–12 分钟 | 先提炼 1–3 个核心论点，其余舍弃 |

超长文两段式：先出论点大纲，再据此写剧本。

## 8. 字幕与音轨精度

- 每句单独合成，用 `ffprobe` 取真实时长，累加得起始偏移；字幕与音频严格对齐。
- 主音轨拼接：每句 mp3 → 统一 44100Hz 单声道 wav → Python `wave` 模块按顺序写入，句间插入 `pause_after_ms` 静音 → ffmpeg 编码 mp3。
- 分角色音轨：遍历全部句子，匹配当前角色的写入音频，其余位置写等长静音，保证与主音轨时长一致。

## 9. 错误处理

| 情况 | 处理 |
|---|---|
| PDF 扫描件（无文字层） | 提取字数 < 100 时报错，提示先 OCR |
| 网页抓取失败 | 回退简单正文启发式，再失败提示手动粘贴 |
| 单句 TTS 失败 | 重试 3 次，仍失败则跳过该句并在最后汇总（时间轴按实际成功的句子重算，不会错位） |
| 原文过短（< 300 字） | 警告并询问是否继续 |
| 字数偏离目标 > 40% | 报告提示，不静默放过 |

## 10. 测试

- fixtures：短 md、PDF、标准 script.json
- 单测：extract 各格式、tts 用 mock 引擎、srt 时间轴单调递增且总长误差 < 100ms
- 端到端：mock TTS 跑通全流程，产出四个文件
