---
name: xiaopin
description: 把 PDF / Word / 网页链接 / Markdown / 纯文本改写成多角色喜剧小品（相声/对谈/科普亦可），自动配音并输出完整 mp3、srt 字幕、可读剧本和分角色音轨。触发词：做成小品、改成小品、做成相声、把这篇改编成对话、配音小品、/xiaopin。
---

# 小品工厂

把一篇文章变成一出能听的、有配音的多角色小品。

## 快速开始

```bash
python scripts/extract.py <文件或URL> -o work/source.json
# → Claude 读正文，写 work/script.json
python scripts/tts.py work/script.json -o work
python scripts/assemble.py work -o out
```

产出：`out/<标题>.mp3`、`.srt`、`.md`、`out/tracks/<角色>.mp3`。

## 完整流程

### 第 1 步：抽取正文

```bash
python scripts/extract.py "<路径或URL>" -o work/source.json
```

注意脚本输出到 stderr 的 `[警告]`：

- 「正文只有 N 字」→ 大概率是扫描版 PDF。**停下来告诉用户需要先 OCR**，不要硬编。
- 字数 < 300 → 问用户是否仍要生成。

读取 `work/source.json`，其中 `title`、`char_count`、`text` 是后续所有判断的依据。

### 第 2 步：决定参数

按用户要求确定三件事，用户没说的用默认：

| 参数 | 默认 | 何时改 |
|---|---|---|
| 风格 | 用户说了就照做，没说选最贴切的 | 学术论文→科普或喜剧；观点文→对谈；故事→喜剧；教程→科普 |
| 角色数 | 2 | 用户指定 N 就按 N |
| 目标时长 | 由原文长度自动定 | 用户指定就按用户的 |

时长换算（详见 `references/styles.md`）：

- 原文 < 2000 字 → 3-5 分钟，台词 800-1200 字
- 原文 2000-8000 字 → 6-9 分钟，台词 1500-2400 字
- 原文 > 8000 字 → **先提炼大纲**（见下），再写，台词 2400-3000 字

**超过 8000 字时不要直接读全文写剧本**：先在 `work/outline.md` 里提炼 1-3 个核心论点、可用作包袱的素材、必须保留的关键事实，然后只依据大纲写剧本。

### 第 3 步：写剧本

**动手前必读**：`references/styles.md`（所选风格的结构与技法）和 `references/script-schema.md`（JSON 契约与硬性要求）。

写 `work/script.json`。硬性要求再强调一遍：

- **单句 ≤ 40 字**。超了 TTS 会念平，笑点掉。
- **一句一行**，同一人连说三句也拆三条。
- **口语**，禁止「综上所述」「值得注意的是」「本文将」。
- **不许照抄原文句子**，改写成人话。
- **角色音色不重复**，优先用方言音色拉开反差。
- **停顿有节奏**：包袱前 400ms、包袱后 600-800ms、换场 1000ms。

写完后自查一遍：数一下总字数是否落在目标区间（偏差 > 40% 就调整），检查每个 `speaker` 都在 `characters` 里。

### 第 4 步：合成与拼装

```bash
python scripts/tts.py work/script.json -o work --workers 8
python scripts/assemble.py work -o out
```

`tts.py` 会**并发**逐句合成（默认 6 线程，`--workers` 可调，edge-tts 建议不超过 8）、用 ffprobe 取真实时长、生成 `manifest.json`。失败句子会重试 3 次，仍失败则跳过并在最后汇总——**看到 failures 不为空要告诉用户**。

`assemble.py` 输出四类文件并校验音画时长一致。

### 第 5 步：交付

报告给用户：

- 成片时长、句数、风格、用了哪些角色和音色
- 四个产物的路径
- 任何警告（TTS 失败、字数偏差、原文偏短）

不要复述整个剧本内容，用户会自己打开 md 看。

## 表演调节（逐句语速/音高）

角色的 rate/pitch 是全程固定的，但贯口要加速、复读要递进、包袱要刹车。用 `tune.py` 批量设置：

```bash
# 先看某段
python scripts/tune.py work/script.json --show 89:130

# 数来宝逐句加速 +0% → +25%，同时升调
python scripts/tune.py work/script.json --ramp 89:130 --rate-from 0 --rate-to 25 --pitch-from 0 --pitch-to 4

# 包袱前突然刹车
python scripts/tune.py work/script.json --set 175:176 --rate -15

# 冷面台词
python scripts/tune.py work/script.json --set 293:293 --rate -12 --pitch -4
```

必须处理的四类段落：

| 段落 | 处理 |
|---|---|
| 贯口 / 数来宝 | 逐句加速到 +25~30% |
| 复读递进（连喊同一句） | 逐句加速 + 升调，最后一句最高 |
| 包袱刹车（「一样儿不卖——退款」） | 突然降到 -15% |
| 冷面台词（「已激活」） | -10~-15%，降 3~5Hz |

调节只改剧本，不动音频；改完重跑 `tts.py` 即可。

## 已有剧本直接导入

如果输入本身就是一份写好的小品/相声剧本（不是文章），**不要重写**，直接导入：

```bash
python scripts/import_script.py 剧本.md -o work/script.json \
    --style xiangsheng \
    --voice-a zh-CN-YunjianNeural --rate-a=+5% \
    --voice-b zh-CN-XiaoxiaoNeural --rate-b=-3%
```

它会：

- 只解析「第X折/幕/场」到「演出提示」之间的正戏，跳过人物表、道具、附录
- 识别 `**甲**（舞台提示）：台词` 格式，把舞台提示抽成 `emotion`
- 把 `>` 引用块（数来宝、贯口）归给当前说话人
- 按标点把长句切到 45 字以内
- 按句末标点设停顿，`【抖包袱】` 前一句自动加到 800ms
- 输出字数与预计时长

导入后先抽查开头、中段、结尾各 10 句，确认没有丢词再合成。多角色剧本用 `--roles` 不适用，音色需手工改 `script.json`。

注意：`--rate-b=-3%` 必须用等号，否则 `-3%` 会被 argparse 当成选项。

## 引擎切换

默认 edge-tts，零配置。要换引擎：

```bash
cp config.example.json config.json   # 首次
# 编辑 config.json 的 "engine" 字段
python scripts/tts.py work/script.json -o work --engine openai
```

- `edge`：免费，无需 key，方言音色
- `openai`：需 api_key，音色名换成 OpenAI 的（alloy/echo/fable/onyx/nova/shimmer）
- `local`：指向本地 HTTP 服务（CosyVoice / GPT-SoVITS / Fish Audio）

换引擎时角色音色名要跟着换，否则会静默用默认音色。

## 常见问题

| 症状 | 处理 |
|---|---|
| PDF 提取出乱码 | 扫描件，让用户先 OCR |
| 网页抓不到正文 | 让用户手动复制正文存成 .txt 再跑 |
| 剧本报错 speaker 不在 characters | 补声明或改 id |
| 音频里有两个角色声音一样 | 音色配重了，改 characters 里的 voice |
| 字幕比声音快/慢 | 不应发生（逐句 ffprobe 计时），若出现检查 ffmpeg 是否在 PATH |
