# 小品工厂（xiaopin）

把一篇文章变成一出**能听的、有配音的多角色小品**。

丢进来一个 PDF / Word / 网页链接 / Markdown / 纯文本，出来四样东西：

- 🎧 完整音频 `mp3`（多角色不同音色交替）
- 📝 可读剧本 `md`
- 💬 字幕 `srt`（丢进剪映直接配字幕）
- 🎚 分角色音轨 `tracks/*.mp3`（便于后期剪辑）

## 装什么

已确认本机具备：Python 3.13 / edge-tts 7.3 / ffmpeg 7.1 / pypdf / python-docx / requests / bs4。

换机器时：

```bash
pip install -r requirements.txt
# ffmpeg 需单独安装并加入 PATH
```

## 怎么用

在 Claude Code 里直接说：

```
把这篇做成小品：D:\docs\某篇文章.pdf
```

或者指定风格和人数：

```
把这篇论文做成三人相声，3 分钟
```

斜杠命令（装了 skill 后）：

```
/xiaopin D:\docs\文章.pdf --style xiangsheng --roles 3
```

## 手动跑流水线

```bash
python scripts/extract.py "文章.pdf" -o work/source.json
# 此时由 Claude 读 work/source.json，写 work/script.json
python scripts/tts.py work/script.json -o work --workers 8
python scripts/assemble.py work -o out
```

`--workers` 控制并发线程数（默认 6，edge-tts 建议不超过 8）。

## 已有剧本直接导入

输入本身就是写好的小品/相声剧本时，跳过改写，直接转成可配音的 JSON：

```bash
python scripts/import_script.py 剧本.md -o work/script.json \
    --style xiangsheng \
    --voice-a zh-CN-YunjianNeural --rate-a=+5% \
    --voice-b zh-CN-XiaoxiaoNeural --rate-b=-3%
```

支持 `**甲**（舞台提示）：台词` 与 `>` 引用块（数来宝/贯口），自动切句、设停顿、
在 `【抖包袱】` 前加长停顿。详见 `SKILL.md`。

## 风格

| style | 说明 |
|---|---|
| `comedy` | 喜剧小品：场景冲突 → 误会升级 → 反转 → 升华 |
| `xiangsheng` | 双人相声：一捧一逗、三翻四抖、现挂 |
| `talk` | 播客对谈：真实分歧、口语、举例子 |
| `edu` | 知识科普：一个比喻讲到底 + 外行提问 |

写法细则见 `references/styles.md`。

## 换配音引擎

默认 **edge-tts**：免费、免 key、免显卡，自带东北话和陕西话方言音色——喜剧效果的大半来自音色反差。

换引擎：

```bash
cp config.example.json config.json
# 编辑 config.json 里的 "engine": "edge" | "openai" | "local"
```

| 引擎 | 需要 |
|---|---|
| `edge` | 什么都不需要 |
| `openai` | API Key（任意兼容 `/v1/audio/speech` 的服务） |
| `local` | 本地 TTS HTTP 服务（CosyVoice / GPT-SoVITS / Fish Audio） |

**换引擎时记得同步改 `script.json` 里角色的 `voice`**，否则会静默回退到默认音色。

## 目录

```
SKILL.md              触发词与流程编排（Claude 读这个）
scripts/
  extract.py          抽取正文（pdf/docx/url/md/txt）
  tts.py              逐句合成 + ffprobe 计时 → manifest.json
  assemble.py         拼接 mp3 / srt / md / 分角色音轨
  engines/            可插拔 TTS 引擎
references/
  styles.md           四种风格写法 + 音色表 + 时长换算
  script-schema.md    剧本 JSON 契约
examples/demo-comedy.json  一份完整的喜剧剧本示例
tests/                8 个测试，含真实 ffmpeg 端到端
```

## 精度保证

字幕不靠估算：每句单独合成后用 `ffprobe` 取真实时长，累加得出起始偏移。主音轨与分角色音轨时长严格一致（实测 256.705306s 三轨完全相同）。

## 测试

```bash
python -m pytest -q
```
