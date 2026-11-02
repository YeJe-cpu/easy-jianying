# 计划格式（plan）

一个 JSON 文件。时间单位**秒**；坐标 `x, y` 以画面中心为 0，左右/上下边缘为 ±1。

```json
{"name": "草稿名", "canvas": "9:16" | {"width":1080,"height":1920,"fps":30}, "fps": 30,
 "tracks": [ { "type": "...", "name": "可选", "clips": [ ... ] } ]}
```
`canvas` 预设：`16:9` `9:16` `1:1` `4:3` `3:4` `2.35:1`。

同一份计划剪映和 CapCut 通用：`jyr build plan.json ...` 给剪映，`jyr --app capcut build plan.json ...` 给 CapCut。区别只在资源名——资源从各自的资源目录里找（`jyr [--app capcut] catalog list`），CapCut 里没用过的转场 / 动画名字会报错并列出可用的。

## 轨道类型

| type | 说明 |
|---|---|
| `video` | 第一条是主轨（应从 0 连续，否则给警告；`"allow_gaps": true` 关掉警告），后面的是画中画 |
| `audio` | 音乐、配音、音效 |
| `text` | 标题/花字 |
| `subtitle` | 剪映 / CapCut 的「识别字幕」轨（默认白字黑描边、位于下方） |
| `effect` / `filter` | 特效轨 / 滤镜轨 |
| `sticker` | 贴纸 |

## 通用片段字段

| 字段 | 说明 |
|---|---|
| `start` | 在时间线上的开始；不写 = 接在同轨上一段后面 |
| `duration` | 时长；视频/音频不写 = 用到素材结尾（考虑变速） |
| `transform` | `{"x","y","scale","scale_x","scale_y","rotation","opacity","flip_h","flip_v"}` |
| `keyframes` | `{"x"|"y"|"scale"|"scale_x"|"scale_y"|"rotation"|"opacity"|"volume": [[秒, 值], ...]}`，时间相对片段开头、递增、在片段内 |
| `anim` | `{"in": "名字", "out": "名字", "loop": "名字"}` 或 `{"in": {"name": "...", "duration": 0.5}}`；名字可写 `"auto"` |

## video / audio 片段

| 字段 | 说明 |
|---|---|
| `src` | 素材路径；相对路径按计划文件所在目录解析 |
| `in` / `out` | 素材内的入点 / 出点（秒） |
| `speed` | 0.1–100 |
| `volume` | 0 静音，1 原声，可 >1 |
| `fade` | `{"in": 秒, "out": 秒}` 声音淡入淡出 |
| `transition` | 只在 video 主轨：`"叠化"` 或 `{"name": "叠化", "duration": 0.5}`；挂在本段与下一段之间 |
| `mask` | `{"shape": "circle|rectangle|line|mirror|heart|star 或中文名", "width", "height", "x", "y", "feather", "rotation", "invert", "round_corner"}` |
| `effects` | `["特效名", ...]` 只作用于本段 |
| `beats` | `[秒, ...]` 踩点标记（相对本段开头） |
| `reverse` | 倒放 |

## text / subtitle 片段

| 字段 | 说明 |
|---|---|
| `text` | 文字 |
| `style` | `{"size", "color": "#RRGGBB", "font": "字体名 / 绝对路径 / auto:title|subtitle|body|handwriting|cute", "bold", "italic", "stroke": {"color", "width"}, "background": "#RRGGBB", "align": "left|center|right", "line_spacing", "letter_spacing"}` |
| `words` | 识别字幕的逐字时间（一般由 `jyr subtitles` 生成） |

## effect / filter / sticker 片段
`{"name": "资源名或 auto", "start", "duration"}`，sticker 另有 `transform`、`anim`、`keyframes`。

资源名查询：`jyr catalog list transition|mask|effect|filter|animation|font|sticker`；CapCut 加 `--app capcut`，`--free` 只看免费的。

**资源只用免费的。** 内置清单只收剪映 / CapCut 自己在草稿 `key_value.json` 里记为免费（`is_vip` 0）的资源，加上 App 安装包自带的字体。`"auto"` 只挑免费的；点名用了会员 / Pro 资源（来自你自己 `catalog scan` 的结果），`build` 的 `warnings` 里会提醒。剪映内置清单里没有蒙版和文字动画——需要的话在剪映里手动加，`mask` / `anim` 字段只在清单里有对应资源时可用。
