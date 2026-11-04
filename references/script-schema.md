# 剧本 JSON 契约

`script.json` 是流水线唯一的中间产物：Claude 写它，`tts.py` 读它。

## 结构

```json
{
  "title": "标题",
  "style": "comedy | xiangsheng | talk | edu",
  "source": {"file": "原文路径或URL", "char_count": 3200},
  "characters": [
    {
      "id": "A",
      "name": "老张",
      "persona": "轴，认死理，说话爱抬杠",
      "voice": "zh-CN-liaoning-XiaobeiNeural",
      "rate": "-5%",
      "pitch": "+0Hz"
    }
  ],
  "lines": [
    {
      "speaker": "A",
      "text": "台词",
      "emotion": "急",
      "pause_after_ms": 600
    }
  ]
}
```

## 字段规则

| 字段 | 必填 | 说明 |
|---|---|---|
| `title` | 是 | 小品标题，也用作输出文件名 |
| `style` | 是 | 四选一 |
| `characters[].id` | 是 | 简短唯一标识，建议 A/B/C |
| `characters[].name` | 是 | 显示名，如「老张」「小刘」 |
| `characters[].persona` | 是 | 一句话人设，决定说话方式 |
| `characters[].voice` | 是 | 音色名，见 styles.md 音色表 |
| `characters[].rate` | 否 | 语速，如 `-8%` / `+10%`，默认 `+0%` |
| `characters[].pitch` | 否 | 音高，如 `-4Hz` / `+6Hz`，默认 `+0Hz` |
| `lines[].speaker` | 是 | 必须是已声明的角色 id |
| `lines[].text` | 是 | 单句 **不超过 40 字**（硬上限 80），超了字幕会挤 |
| `lines[].emotion` | 否 | 情绪标签，只写进可读剧本，供配音参考 |
| `lines[].pause_after_ms` | 否 | 本句后的停顿。包袱后 500-800ms，换场 1000ms |

## 写作硬性要求

1. **一句一行，不合并**。哪怕同一个人连说三句，也拆成三条，方便字幕和后期剪辑。
2. **单句 ≤ 40 字**。中文 TTS 一口气念 40 字以上会开始平，笑点会掉。
3. **停顿要有节奏**：抛包袱前 400ms，包袱后 600-800ms，段落转换 1000ms。
4. **口语，不是书面语**。不许出现「综上所述」「值得注意的是」「本文将」。
5. **不许照抄原文句子**。必须改写成人话，必要时用比喻和例子替代术语。
6. **开场 15 秒内必须抛出钩子**，结尾要回扣开头。

## 常见错误

- 角色 id 写了但没在 `characters` 里声明 → `tts.py` 会直接报错
- 一个角色的音色和另一个人重复 → 听不出来，务必配不同音色
- 台词塞满原文所有细节 → 删。小品只留 1-3 个核心点，其余当包袱用
