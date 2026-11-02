# 它是怎么做到的

剪映（macOS 专业版）的一个草稿就是 `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/<名字>/` 下的一个文件夹（CapCut 在 `~/Movies/CapCut/User Data/...`）。jyr 做的事情只有一件：**按剪映自己的格式把这个文件夹写出来，登记到首页**。打开、编辑、导出都在剪映里完成。

## 1. 格式：向剪映自己学

时间线在 `draft_info.json` 里：`tracks`（轨道 → 片段）+ `materials`（素材表），片段用 id 引用素材。我们的格式知识**全部来自剪映自己存出来的草稿**——只挑作者在剪映界面里亲手剪的那些，逐个功能对照：

| 功能 | 剪映怎么记 |
|---|---|
| 变速 | 片段 `speed` + 一个 `speeds` 素材 |
| 转场 | 挂在**前一个**片段的 `extra_material_refs` 上；相邻片段首尾相接、不重叠；时长取偶数帧 |
| 视频片段的声音淡入淡出 | 片段引用一个 `audio_fades` 素材，**同时**这个视频素材本身也带一份 `audio_fade`——所以剪映一个片段一份视频素材 |
| 关键帧 | 片段 `common_keyframes`，属性名 `KFTypePositionX / ScaleX / Alpha / Rotation / Volume…`，时间相对片段开头 |
| 识别字幕 | 文字素材 `type: "subtitle"` + 文字轨 `flag: 1` + 逐字 `words` |
| 踩点 | 音频片段引用 `beats` 素材，`user_beats` 用**素材内**时间 |
| GIF | 素材类型 `gif`，时长和图片一样记 3 小时（循环） |
| 片段边界 | 一律对齐到帧网格 |

剪映 11.x 存盘时会省略默认值，所以我们只写剪映自己会写的字段。

## 2. 写文件：普通 JSON

`draft_info.json`（时间线）、`draft_meta_info.json`（素材表、文件夹信息）等都按普通 JSON 写出。实测剪映 11.7 能直接打开、播放、编辑、导出；剪映保存后会按它自己的格式存，jyr 不再读这些文件——要改就改计划重新生成，或者在剪映里改。

## 3. 资源：只放免费的

转场/特效/动画/贴纸/字体是剪映的原生资源，草稿里只记"说明卡"（名字、资源编号、剪映的记录字段），效果文件在剪映缓存里。

- 仓库自带 `jyr/data/resources.json`：**只收免费资源**。依据是剪映在每个草稿文件夹里记的 `key_value.json`——它给用过的每个资源记了 `is_vip`，为 0 才收；再加上剪映安装包自带的字体。会员资源（67 个）和查不到记录的（133 个）都不放，最后 175 张卡。生成方法：`tools/build_resource_pack.py`。
- 说明卡去掉了本机路径、带签名的预览链接、每次使用的 id。
- 实测（11.7）：草稿里写的路径错了也没关系，剪映按编号找；缓存删掉了，剪映打开草稿时会自己重新下载效果和字体。
- `"auto"` 只在免费资源里挑；字体按"你在标题/字幕里分别用过哪些"+ 字体名风格来挑，系统字体只保留能显示中文的。
- 会员效果、蒙版、文字动画这类清单里没有的，请在剪映里手动添加。

## 4. 剪映升级

jyr 只需要知道一件跟版本有关的事：这个版本的剪映写什么样的时间线版本号（`new_version`，11.5 → 187.0.0，11.6 / 11.7 → 189.0.0）。

`jyr doctor` 从剪映安装包的 Info.plist 读版本号。遇到表里没有的新版本，`jyr adapt` 先按已知最新的时间线版本号走，存进 `~/.jyr/profiles.json`；生成一份草稿在剪映里打开确认就行。

## 5. CapCut 国际版

CapCut 和剪映用同一种草稿格式（`version 360000`），而且 CapCut 自己存的草稿也是普通 JSON。所以 CapCut 一侧既能写也能读：

- **认 App**：`runtime.App` 记着两家的 bundle id、数据目录、进程名、`platform.app_id/app_source`（剪映 3704 / `lv`，CapCut 359289 / `cc`）。`--app capcut`、`JYR_TARGET`、`JYR_APP` 指向谁就用谁；只装一个就用它。
- **时间线版本号**：从 CapCut 自己存的草稿里读——只认 `last_modified_platform` 的版本与本机 CapCut 相同、`app_source` 为 `cc` 的，取最大的 `new_version`（9.4.1 → 185.0.0）。
- **写**：字段和剪映完全相同，只换 `platform` 与 `new_version`；首页索引 `root_meta_info.json` 字段也相同，推送前同样要求 CapCut 完全退出、先备份索引。
- **读**：`inspect` / `srt` / `edit` 直接读 JSON。
- **资源**：老资源（如动画「放大」「向右甩入」）两家共用编号，新资源不共用，所以 CapCut 有自己的目录 `~/.jyr/catalog-capcut.json`。每个草稿文件夹里的 `key_value.json` 记着用过的资源 `is_vip`，扫描时据此打上免费 / Pro；内置包 `jyr/data/resources.capcut.json` 只收免费的（`tools/build_resource_pack.py --app capcut`）。
- **验收**：人在 CapCut 里打开、播放、自己导出。
