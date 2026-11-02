<div align="center">

# Easy JianYing

**Tell your AI what to cut. Get a real, editable JianYing (剪映) project back.**

Transitions, keyframes, subtitles, beat-sync, talking-head rough cuts — all as native JianYing tracks you can drag and tweak, then finish in JianYing.

[中文](README.md) · [Quick start](#quick-start) · [How it works](docs/how-it-works.md) · [CapCut](#capcut)

<img src="docs/media/hero.gif" width="640" alt="A draft generated from a JSON plan, opened and played in JianYing 11.7">

<p>A JSON plan became a draft, <b>opened in JianYing 11.7</b>.<br>(The small circle at the top right is a picture-in-picture with a circle mask, which is a member resource — see below.)</p>

</div>

---

## Why a draft, not a finished video

AI-made videos are often one or two details away from done: a typo in a subtitle, a shot half a second too long, music a bit too loud.

With a finished video, every fix means going back to the AI, regenerating and re-rendering — more waiting, more compute, and no guarantee the result is what you wanted. With a JianYing draft, you open JianYing, fix the subtitle, trim the clip and finish.

| Fix one typo | Finished video | JianYing draft |
|---|---|---|
| How | Regenerate and re-render | Double-click the subtitle in JianYing |
| Wait | Another full render | Seconds |
| Compute | Spent again | None |

> **AI writes the edit plan → we generate a native JianYing draft → you open it and fine-tune.**

<div align="center"><img src="docs/media/timeline-multitrack.jpg" width="820" alt="JianYing timeline with main track, transitions, speed ramp, two picture-in-pictures, title, subtitles and music"></div>

## What it does

| | Feature | What it means |
|---|---|---|
| 🎬 | **Generate drafts** | Multi-track, chop, speed, transitions, keyframes, PiP, text, subtitles, stickers, effects, filters, music fades, images/GIF |
| ✂️ | **Talking-head rough cut** | Cuts dead air, fillers, stutters and false starts; then an agent drops the sentence you said twice |
| 💬 | **Auto subtitles** | Local speech recognition (nothing uploaded) → JianYing's native caption track |
| 🥁 | **Beat sync** | Detects the beat, cuts footage on it, adds JianYing beat markers |
| 📦 | **Batch** | One template × one spreadsheet = N drafts |
| 🎨 | **Auto picks** | `"auto"` transitions / effects / fonts, chosen from free resources only |
| 👑 | **Member resources** | JianYing members add `--member` and the AI can use paid transitions, masks, text animations |
| 🌏 | **CapCut** | The same plan makes a CapCut draft |

You open, fine-tune and render the draft in JianYing / CapCut; paid features follow the app's own rules.

## Free users get free resources, members get theirs

Transitions, effects, stickers and fonts are the app's own resources: a draft only names them by ID, and the app downloads the files.

JianYing records in each draft folder's `key_value.json` whether a resource it used is paid (`is_vip`). Easy JianYing marks all 375 built-in cards with it: **175 free** (`is_vip` 0, or fonts bundled with JianYing), 67 paid, 133 with no record.

- **By default only free ones are used**: 116 stickers, 28 effects, 23 fonts, 5 transitions, 1 animation, 1 filter, 1 audio effect. `"auto"` only picks from these.
- **If you are a JianYing member**, add `--member` (or `"member": true` in the plan) and paid or unrecorded resources can be named too — paid transitions, masks, text animations. The build warns which ones are paid.
- Once the draft is open, JianYing applies its own membership rules as usual; jyr does not get around any check.

## Tested versions

jyr writes ordinary JSON draft files; the apps open, edit, save and render them as usual.

| App | Tested | Create drafts | Read / SRT / edit a copy |
|---|---|:---:|:---:|
| JianYing Pro (macOS) | 11.7.0 | ✅ | only drafts jyr built that JianYing has not saved yet |
| CapCut (macOS) | 9.4.1 | ✅ | ✅ (CapCut drafts are plain JSON) |

Other versions are untested. After a JianYing update run `jyr adapt`, then open one built draft to confirm.

## CapCut

Same plan, add `--app capcut`, get a CapCut draft:

```bash
jyr --app capcut doctor
jyr --app capcut build examples/capcut.plan.json --out /tmp/cc-demo --publish --name "my first CapCut draft"
jyr --app capcut inspect "my first CapCut draft"   # read, write SRT, edit a copy
```

With only one of the two apps installed, `--app` is optional; with both, JianYing is the default. On the CapCut side the tool **only reads and writes draft files**; it uses nothing inside CapCut and never touches its UI.

CapCut's resource IDs only partly match JianYing's, so it has its own list. Built in are mostly CapCut's bundled fonts; anything you have used once in CapCut becomes usable after `jyr --app capcut catalog scan`. Same rules as JianYing: free by default, CapCut Pro users add `--member` for Pro resources; `catalog list --free` lists only free ones.

## Quick start

macOS + JianYing Pro (or CapCut), Python 3.10+, ffmpeg.

```bash
git clone https://github.com/YeJe-cpu/easy-jianying && cd easy-jianying
pip install -e '.[asr,fonts]'
jyr doctor
./tools/make_fixtures.sh examples/media
jyr build examples/showcase.plan.json --out /tmp/jyr-demo --publish --name "my first AI draft"
```

Quit JianYing before publishing; the new draft appears first on its home screen. Plan reference: [docs/plan-format.md](docs/plan-format.md). Agent skills: [`skills/`](skills/).

## How we checked it

1. **Every feature was looked at in JianYing.** Real footage, opened, played and rendered in JianYing, checked by eye. Records: [docs/acceptance.md](docs/acceptance.md).
2. **Missing effects get downloaded by JianYing.** Delete a transition's or font's cache and JianYing fetches it again by ID when the draft opens.
3. **The rough cut is graded against a human editor.** On a 316 s raw take, the human cut was 232 s. Rules alone gave 250 s and kept 99% of what the human kept; one agent pass got it to 242 s.
4. **The beat sync is frame-accurate.** On a metronome at 90–150 BPM: tempo error ≤1.5%, beat position off by 2 ms on average and 5 ms at most.
5. **Built for agents.** Times are in seconds, clips chain automatically, resources go by their UI names, and errors list the options that are available.

## Limits

macOS only: tested on an Intel Mac with JianYing 11.7 and CapCut 9.4.1. Apple Silicon should work but hasn't been tested; Windows is untested. jyr only writes draft files and never operates the apps' UI — opening, editing and rendering happen in the app. jyr does not read drafts JianYing has saved (CapCut drafts it can read). Only free resources are used unless you declare membership with `--member`; JianYing's membership rules apply either way. Whether CapCut downloads a missing effect by ID, as JianYing does, has not been checked on another machine yet. Not yet supported: crop, chroma key, color grading, curve speed, styled text and audio effects. **Unofficial; not affiliated with ByteDance.** JianYing's / CapCut's terms of use apply.

## Credits

[pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft), [capcut-cli](https://github.com/renezander030/capcut-cli), Dan Ellis's beat tracking and [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Thanks also to Yichen's (mcncarl) jianying-headless: we first used and adapted it locally, and after it was taken down we rewrote this project from scratch. It contains none of that project's code or data.

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md). Free for learning, research and other non-commercial use. Commercial use (paid courses, paid services, client work) needs permission from the author.

## Contact

X [@leaf_sanren](https://x.com/leaf_sanren) for chats and feedback (or open an issue); commercial licensing: [aiesecxuanli@gmail.com](mailto:aiesecxuanli@gmail.com). Also by the author: [SeeCut](https://github.com/YeJe-cpu/SeeCut).
