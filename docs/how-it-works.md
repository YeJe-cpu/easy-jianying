# 它是怎么做到的

剪映（macOS 专业版）的一个草稿就是 `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft/<名字>/` 下的一个文件夹。要用代码写草稿，要解决四件事。

## 1. 格式：向剪映自己学

时间线在 `draft_info.json` 里：`tracks`（轨道 → 片段）+ `materials`（素材表），片段用 id 引用素材。我们的格式知识**全部来自剪映自己存出来的草稿**——在作者本机上解密了 184 个草稿，只挑作者在剪映界面里亲手剪的那些，逐个功能对照：

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

## 2. 加密：借用你本机的剪映

剪映 6.0 起草稿（`draft_info.json`、`draft_meta_info.json`）是加密的。我们不破解算法，而是：

- 用 `nm` 看 `libvideoeditor.dylib`（剪映自带）导出的符号，找到 `lvve::EncryptUtils::{enable, encrypt, decrypt}`；
- 用 `otool` 看反汇编，确认它们是成员函数（第一个参数是 `this`，但状态存在全局，实例本身没有字段）、`encrypt` 走返回值指针；
- 据此写一个 50 行的 C++ 小程序 `jyr/jyr_crypt.cpp`，链接到你本机剪映里的这个库，文件进、文件出。

坑：这个库一加载就往 stdout 打印横幅（静态初始化时，`main()` 还没跑），所以不能用管道，只能读写文件。

每次写入前我们都会做一次"加密→再解密→和原文逐字节比对"，对不上就不写。

## 2.5 剪映 11.7：钥匙收进了剪映自己手里

11.7 的 `libvideoeditor.dylib` 导出符号和 `decrypt` 外壳与 11.6 逐字节相同，但 `decrypt` 返回"成功 + 空内容"，连自己加密的内容都解不回来。库里新增了 `lvve::ICryptoKeyStore`（全局密钥文件在 `User Data/Config/crypto_key_store.dat`），`ICryptoKeyStore::create(...)` 从外部调用返回空指针——推断密钥由剪映进程启动时注入。我们**没有继续挖**。

改为明文写入：`draft_info.json` / `draft_meta_info.json` 写明文，剪映打开后自己加密存盘。11.7 及以后只写不读；`jyr adapt` 自动识别。

## 3. 资源：内置说明卡 + 从你的草稿里学

转场/蒙版/特效/动画/贴纸/字体是剪映的原生资源，草稿里只记"说明卡"（名字、资源编号、剪映的记录字段），效果文件在剪映缓存里。

- 仓库自带 `jyr/data/resources.json`：375 张说明卡（去掉了本机路径、带签名的预览链接、每次使用的 id）。
- 实测（11.7）：草稿里写的路径错了也没关系，剪映按编号找；缓存删掉了，剪映打开草稿时会自己重新下载效果和字体。
- 剪映 ≤11.6 时，`jyr catalog scan` 还能从你自己的草稿里学到更多（比如你常用的冷门效果），和内置卡合并，你自己的优先。
- `"auto"` = 你用得最多的那个；字体按"你在标题/字幕里分别用过哪些"+ 字体名风格来挑，系统字体只保留能显示中文的。

## 4. 验收与导出：用"辅助功能"开剪映

没有截图权限也能验收：剪映的界面元素在 macOS 无障碍树里有名字（首页卡片 `HomePageDraftTitle:<名字>`、导出按钮 `MainWindowTitleBarExportBtn`、确认 `ExportOkBtn`……）。`jyr/ui.py`：
- 用 System Events 读界面元素的名字和位置；
- 用 CoreGraphics 发真实鼠标点击（剪映不认 AppleScript 的模拟点击）；
- 用菜单"退出"关闭（剪映会拒绝 AppleScript 的 quit）；
- 遇到"链接媒体"弹窗按 Esc，导出完成面板点"关闭"。

剪映打开草稿时会按自己的格式重存一遍。所以 `tools/ui_accept.py` 的判据是：**剪映重存后，轨道、每段的起止时间、各类素材数量、关键帧数量都和我们写的一致**。

导出同理：打开草稿 → 导出 → 确认 → 等完成面板 → 搬文件（`.mp4` 目标做一次无损封装转换）。

## 5. 剪映升级

`jyr adapt`：
1. 确认加密符号还在（不在就停，绝不硬写）；
2. 针对新的库重新编译小桥；
3. 找一份"最后由这个版本保存"的草稿，解密、回加密逐字节比对；
4. 读出这个版本写的时间线版本号（11.5 → 187.0.0，11.6 → 189.0.0），存进 `~/.jyr/profiles.json`。

`--auto`：没有样本时，自己打开剪映点"开始创作"再退出，让剪映存一份。

## 6. CapCut 国际版：只碰明文文件

CapCut 和剪映用同一种草稿格式（`version 360000`），但 CapCut 的草稿**从不加密**。所以 CapCut 一侧只做文件读写：

- **认 App**：`runtime.App` 记着两家的 bundle id、数据目录、进程名、`platform.app_id/app_source`（剪映 3704 / `lv`，CapCut 359289 / `cc`）。`--app capcut`、`JYR_TARGET`、`JYR_APP` 指向谁就用谁；只装一个就用它。CapCut 程序里也带 `libvideoeditor.dylib`，jyr 不链接、不调用、连哈希都不算。
- **时间线版本号**：从 CapCut 自己存的草稿里读——只认 `last_modified_platform` 的版本与本机 CapCut 相同、`app_source` 为 `cc` 的，取最大的 `new_version`（9.4.1 → 185.0.0）。
- **写**：字段和剪映完全相同，只换 `platform` 与 `new_version`；首页索引 `root_meta_info.json` 字段也相同，推送前同样要求 CapCut 完全退出、先备份索引。
- **读**：`inspect` / `srt` / `edit` 直接读明文 JSON，不经过任何解码。
- **资源**：老资源（如动画「放大」「向右甩入」）两家共用编号，新资源不共用，所以 CapCut 有自己的目录 `~/.jyr/catalog-capcut.json`。每个草稿文件夹里明文的 `key_value.json` 记着用过的资源 `is_vip`，扫描时据此打上免费 / Pro；内置包 `jyr/data/resources.capcut.json` 只收免费的（`tools/build_resource_pack.py --app capcut`）。
- **不做**：不驱动 CapCut 界面，所以没有 CapCut 的 `export`、`adapt --auto`、`tools/ui_accept.py`；验收靠人在 CapCut 里打开、播放、导出。
