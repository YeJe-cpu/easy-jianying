---
name: jianying-draft
description: 用代码生成 / 读取 / 修改 / 导出 剪映专业版(macOS) 草稿。多轨、切碎、变速、转场、蒙版、关键帧、画中画、文字与识别字幕、贴纸、特效滤镜、BGM 淡入淡出、踩点；改已有草稿（替换文字、重新链接丢失素材、加字幕）；让剪映自己导出成片；剪映升级后自动适配。当用户说"用代码做剪映草稿 / 生成剪映工程 / 把素材拼进剪映 / 改剪映草稿 / 剪映导出 / 剪映升级了"时使用。
---

# jyr · 剪映草稿（核心）

所有命令：`jyr <命令>`（未安装时在仓库根目录用 `python3 -m jyr <命令>`）。

## 0. 第一次用 / 剪映升级后
```bash
jyr doctor            # 找到剪映、编译加密桥、试解一份草稿；status 应为 ok
jyr catalog scan      # 扫你用过的转场/蒙版/特效/动画/字体，生成资源目录（约 1–3 分钟）
jyr adapt --auto      # 剪映升级后报 "has not been adapted" 时跑；全自动
```

## 1. 写计划 → 生成草稿 → 上剪映首页
计划是 JSON，时间单位**秒**。最小示例：
```json
{"name": "我的草稿", "canvas": "9:16",
 "tracks": [
  {"type": "video", "clips": [
    {"src": "/abs/a.mp4", "in": 2, "duration": 3, "transition": "叠化"},
    {"src": "/abs/b.mp4", "duration": 4, "speed": 1.5, "fade": {"out": 1}}]},
  {"type": "text", "clips": [{"text": "标题", "start": 0.5, "duration": 3,
     "style": {"font": "auto:title", "size": 12, "color": "#FFD400", "stroke": {"color": "#000000"}},
     "transform": {"y": 0.6}, "anim": {"in": "auto"}}]},
  {"type": "audio", "clips": [{"src": "/abs/bgm.mp3", "volume": 0.6, "fade": {"in": 1, "out": 2}}]}]}
```
```bash
jyr build plan.json --out /abs/work/build1 [--publish] [--name 名字]
jyr publish /abs/work/build1 --name 名字      # 剪映必须完全退出
```
字段全集见 `docs/plan-format.md`。要点：
- 片段不写 `start` 就接在同轨上一段后面；不写 `duration` 就用到素材结尾。
- 资源用剪映界面里的中文名：转场 `"叠化"`、蒙版 `{"shape":"circle"}`、动画 `{"in":"打字机 I"}`、特效轨 `{"type":"effect","clips":[{"name":"模糊"}]}`。名字找不到时报错会列出可用项；`jyr catalog list transition` 也能看。
- `"auto"` = 用你最常用的那个；字体 `"auto:title|subtitle|body|handwriting|cute"`。
- 第一条 video 轨是主轨，应从 0 开始、连续；画中画放后面的 video 轨。
- 转场挂在前一段上，后面必须紧接下一段；末段不能有转场。

## 2. 读 / 改已有草稿（永远改副本）
```bash
jyr list                               # 首页草稿
jyr inspect "草稿名"                   # 轨道、文字、丢失素材、用到的资源
jyr srt "草稿名" --out a.srt           # 导出字幕
jyr edit "草稿名" --replace "旧=>新" --relink-dir ~/素材 --add-srt a.srt --name 新名字
```
`--ops ops.json` 支持：replace_text / relink / track_volume / remove_tracks / add_subtitles / shift。

## 3. 导出成片（剪映自己渲染）
```bash
jyr export "草稿名" --out /abs/out.mp4
```
沿用剪映上次的导出设置；需要"辅助功能"权限。导出前剪映会被打开、导出后退出。

## 安全
- `build` 不碰剪映；`publish/edit` 只**追加**首页条目，写前自动备份到 `~/.jyr/backups/`；剪映开着会拒绝。
- `edit` 永远在副本上改，原草稿不动。
- publish 前抽帧看一眼素材本身（黑屏/占位图引擎查不出来）。
- 验收：`python3 tools/ui_accept.py BUILD_DIR` 会自动在剪映里打开草稿、让剪映重存、逐项比对。
