<div align="center">

# Easy 剪映

**让 AI 把剪辑做成剪映草稿，你在剪映里接着改。**

转场、关键帧、字幕、卡点、口播粗剪，都会变成剪映里正常的轨道和片段，可以拖、可以改，最后在剪映里自己导出。

[English](README.en.md) · [三分钟上手](#三分钟上手) · [它是怎么做到的](docs/how-it-works.md) · [CapCut 国际版](#capcut-国际版)

<img src="docs/media/hero.gif" width="640" alt="一份 JSON 计划生成的剪映草稿，在剪映 11.7 里打开、播放">

<p>这段画面由一份 JSON 计划生成草稿，在<b>剪映 11.7 里打开、播放</b>。<br>（录于 v0.1。右上角的小圆圈是画中画加了圆形蒙版；v0.2 起蒙版这类效果请在剪映里自己加，见下面「资源只放免费的」。）</p>

</div>

---

## 为什么要做成草稿，而不是直接给成片

AI 剪出来的片子，常常只差一两处：字幕错了一个字，某个镜头长了半秒，音乐想再小一点。

如果拿到的是成片，改这些就得回到 AI 那边重新生成、重新渲染。片子越长，等得越久，每改一次都要再花一次算力，改完还不一定是你想要的。

如果拿到的是剪映草稿，打开剪映，点到那条字幕改掉，把片段拖短一点，在剪映里自己导出就行。

| 想改一个错别字 | 拿到成片 | 拿到剪映草稿 |
|---|---|---|
| 怎么改 | 让 AI 重新生成、重新渲染 | 在剪映里双击字幕，改掉 |
| 要等多久 | 再渲染一遍 | 几秒钟 |
| 算力 | 再花一次 | 不用 |

Easy 剪映做的就是这一步：**AI 写剪辑计划 → 生成剪映草稿 → 你在剪映里打开微调。** 每段素材、每条字幕、每个转场都是独立的片段，和你自己剪的工程没有区别。粗活交给 AI，细节你自己定。

<div align="center">
<img src="docs/media/timeline-multitrack.jpg" width="820" alt="剪映时间线：主轨 4 段 + 叠化/推近转场 + 1.5 倍速 + 两条画中画 + 标题 + 字幕 + BGM">
<p>剪映里看到的就是这样：主轨、转场、变速、画中画、标题、字幕、音乐，各在各的轨道上。</p>
</div>

## 它能做什么

| | 能力 | 具体是什么 |
|---|---|---|
| 🎬 | **生成草稿** | 多轨、切碎、变速、转场、关键帧动画、画中画、文字、字幕、贴纸、特效、滤镜、BGM 淡入淡出、图片/GIF |
| ✂️ | **口播粗剪** | 一条 5 分钟的口播原片，自动剪掉气口、口癖、结巴和说错重来的半句；Agent 再按语义删掉"说了两遍的那句" |
| 💬 | **字幕贴语音** | 本地识别，不上传；生成剪映原生「识别字幕」，在剪映里一键改全部样式 |
| 🥁 | **卡点** | 识别音乐节拍，素材按拍切，再打上剪映原生的踩点标记 |
| 📦 | **批量** | 一个模板 × 一张表格 = N 个草稿，系列视频统一包装 |
| 🎨 | **自动调配** | 转场、特效、字体写 `"auto"`，只在免费资源里挑 |
| 🌏 | **CapCut 国际版** | 同一份计划生成 CapCut 草稿 |

草稿生成后，打开、微调、导出都在剪映 / CapCut 里完成，会员功能照剪映 / CapCut 自己的规则走。

<div align="center">
<img src="docs/media/frames.jpg" width="820" alt="成片抽帧：标题、画中画、字幕">
</div>

## 资源只放免费的

转场、特效、贴纸、字体这些是剪映自己的资源，草稿里只记它们的名字和编号，效果文件由剪映按编号下载。

Easy 剪映内置的资源清单**只收确定免费的**：剪映在每个草稿文件夹的 `key_value.json` 里记着用过的资源是不是会员（`is_vip`），`is_vip` 为 0 的才收；再加上剪映安装包自带的字体。会员资源和查不到记录的都不放。

现在剪映内置 **175 个**免费资源：贴纸 116、特效 28、字体 23、转场 5（推近、叠化、闪黑、滑动、翻页）、动画 1、滤镜 1、音效 1。`"auto"` 也只从这里面挑。会员效果、蒙版、文字动画这些清单里没有的，请打开草稿后在剪映里手动添加。

## 支持哪些版本

jyr 生成的草稿是普通的 JSON 文件，剪映和 CapCut 打开后照常编辑、保存、导出。实测过的版本：

| App | 实测版本 | 生成草稿、放到首页 | 读取 / 导字幕 / 改副本 |
|---|---|:---:|:---:|
| 剪映专业版（macOS） | 11.7.0 | ✅ | 只限 jyr 自己生成、剪映还没存过的草稿 |
| CapCut 国际版（macOS） | 9.4.1 | ✅ | ✅（CapCut 草稿是普通 JSON） |

其他版本没有实测。剪映升级后先跑 `jyr adapt`，再打开一份生成的草稿确认。

## CapCut 国际版

同一份计划，加一个 `--app capcut`，就是一份 CapCut 草稿：

```bash
jyr --app capcut doctor
jyr --app capcut build examples/capcut.plan.json --out /tmp/cc-demo --publish --name "我的第一个 CapCut 草稿"
jyr --app capcut inspect "我的第一个 CapCut 草稿"     # 读草稿、字幕存成 SRT、改副本都行
```

只装了一个就自动用它，不写 `--app` 也行；两个都装时默认剪映。

CapCut 一侧**只读写草稿文件**：不调用 CapCut 程序里的任何东西，也不操作它的界面。

CapCut 的资源编号和剪映不完全一样，所以它有自己的资源清单。内置的只有 CapCut 安装包自带的字体；你在 CapCut 里用过的转场、动画、字体，`jyr --app capcut catalog scan` 扫一遍就能用。扫描同样读 `key_value.json` 区分免费和 Pro：`"auto"` 只挑免费的，计划里点名用了 Pro 资源会给出提醒，`catalog list --free` 只列免费的。

## 三分钟上手

**你需要**：Mac + 剪映专业版（或 CapCut）、Python 3.10+、ffmpeg。

```bash
git clone https://github.com/YeJe-cpu/easy-jianying && cd easy-jianying
pip install -e '.[asr,fonts]'          # 只生成草稿的话 pip install -e . 就够
jyr doctor                             # 检查剪映版本，状态应为 ok

./tools/make_fixtures.sh examples/media
jyr build examples/showcase.plan.json --out /tmp/jyr-demo --publish --name "我的第一个 AI 草稿"
```

推送时剪映要完全退出。打开剪映，首页第一个就是它。

一份计划长这样，时间用秒，资源直接写剪映界面上的中文名：

```json
{"name": "在路上", "canvas": "16:9",
 "tracks": [
  {"type": "video", "clips": [
    {"src": "雪山列车.mp4", "duration": 4, "transition": "叠化"},
    {"src": "牧民.mp4", "duration": 3, "speed": 1.5, "transition": "推近"},
    {"src": "小巷.mp4", "duration": 4.5, "keyframes": {"scale": [[0, 1.0], [4.5, 1.25]]}}]},
  {"type": "text", "clips": [{"text": "在路上", "duration": 3.4,
     "style": {"font": "新青年体", "size": 18, "color": "#FFD400", "stroke": {"color": "#000000"}},
     "keyframes": {"opacity": [[0, 0], [0.6, 1]]}}]},
  {"type": "subtitle", "clips": [{"text": "雪落下的时候", "duration": 3}]},
  {"type": "audio", "clips": [{"src": "bgm.mp3", "volume": 0.7, "fade": {"in": 1, "out": 2}}]}]}
```

给 Agent 用：把 [`skills/`](skills/) 下的 Skill 装进 Claude Code / Codex，直接说"把这条口播粗剪一下放进剪映"就行。

## 我们做了哪些验证

**1. 每个功能都在剪映里看过。**
用真实素材生成草稿，在剪映里打开、播放、导出，人工逐项看轨道、时间和效果。验收记录见 [docs/acceptance.md](docs/acceptance.md)。

**2. 效果缺了，剪映会自己下载。**
实测把转场、字体的缓存删掉，剪映打开草稿时会按编号重新下载回来。

**3. 口播粗剪拿人工剪辑做对照。**
同一条 316 秒的真实口播，人工粗剪到 232 秒。我们只用规则剪到 250 秒，人工保留的内容我们保留了 99%；再让 Agent 读一遍句子，删掉 3 句重复的，剪到 242 秒。

**4. 卡点误差在一帧以内。**
用节拍器测 90–150 BPM：速度误差不超过 1.5%，节拍位置平均差 2 毫秒，最多差 5 毫秒。

<div align="center">
<img src="docs/media/timeline-beats.jpg" width="820" alt="卡点草稿：素材在每个节拍处切换，音乐轨上有剪映原生踩点标记">
</div>

**5. 方便 Agent 使用。**
时间用秒，片段不写开始时间就自动接在上一段后面，资源直接写中文名，写错了会列出可用的选项。口播粗剪留了一步给 Agent 判断语义：停顿和口癖按规则剪，"同一句说了两遍"由 Agent 决定删哪句。

## 边界（先说清楚）

- **只支持 macOS**：剪映专业版 11.7、CapCut 国际版 9.4.1 在 Intel Mac 上实测。Apple Silicon 理论可行，暂未实测；Windows 未测试。
- **jyr 只生成草稿文件，不操作剪映 / CapCut 的界面。** 打开、编辑、导出都由你在 App 里完成。
- **剪映存过的草稿 jyr 不读**：要改就改计划重新生成，或者直接在剪映里改。CapCut 的草稿可以读。
- **内置资源只有免费的**（见上）。会员效果请在剪映里手动添加；会员功能能不能用、能不能导出，以剪映的规则为准。
- CapCut 缺资源时会不会像剪映一样按编号自动下载，还没在别的机器上验证过。
- 还没做的：裁剪、抠图、调色、曲线变速、花字、音频特效。
- 识别字幕会有错字，可以批量替换，也可以接你自己的识别服务。
- **这不是剪映官方工具，和字节跳动没有任何关系。** 剪映 / CapCut 的用户协议依然适用。

## 致谢

- [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)（Gary Guan）——剪映草稿格式研究的开路者。
- [capcut-cli](https://github.com/renezander030/capcut-cli)——公开记录了新版剪映接受普通 JSON 草稿的行为。
- Dan Ellis 的动态规划节拍跟踪；[faster-whisper](https://github.com/SYSTRAN/faster-whisper)。
- 也谢谢逸晨（mcncarl）的 jianying-headless：我们最早是在本机使用并适配它，把它跑通在英特尔 Mac 上，从中学到了很多。它下架后，我们依据自己的实践从头重写了这一版，本仓库不包含它的代码或数据。

## 写在最后

这个项目开始于一个很朴素的情况：一个大家都在用的工具下架了，而我们手上正好有一路踩坑攒下来的经验。

修预览黑屏的时候，我们一度以为是剪映的问题，最后发现是一首 mp3 里嵌了一张专辑封面。这些弯路都记了下来，也写进了代码和测试里。

它一定还有粗糙的地方。如果你发现剪映某个版本又变了、某个功能不对，欢迎告诉我们，也欢迎把你自己的剪辑套路写成新的 Skill。

## 协议

[PolyForm Noncommercial 1.0.0](LICENSE.md)：个人学习、研究、非商业使用都可以，随便改。**不允许商用**（包括卖课、做付费服务、接单交付）；商用请先联系作者。

## 联系作者

- **想聊聊 / 反馈问题**：X（推特）[@leaf_sanren](https://x.com/leaf_sanren)，欢迎私信；也可以直接提 Issue。
- **商业授权与合作**：邮件 [aiesecxuanli@gmail.com](mailto:aiesecxuanli@gmail.com)。
- 同作者的另一个开源项目：[SeeCut](https://github.com/YeJe-cpu/SeeCut)——口播自动精剪成网感动效短视频，也能输出剪映分层草稿。
