# 在 WorkBuddy 中使用

本文按 2026-11-18 的官方文档整理。**本项目尚未在 WorkBuddy 客户端内实测**；技能结构可对接不等于已经验证全部版本、模型和电脑。WorkBuddy 是可选择底层模型的 AI 工作台，不是一个固定模型。执行能力还取决于所选模型、Agent 模式、工具权限和本机环境。[官方简介](https://www.codebuddy.cn/docs/workbuddy/Overview)、[模型配置](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Model)

## 下载与导入

1. 从本仓库 GitHub 页面下载公开技能 ZIP；有 Releases 技能包时优先用该包，否则可用 Code → Download ZIP。先解压检查：技能目录应含 `SKILL.md`、`scripts/`、`references/` 和 `assets/`，不是只有网页或一份说明书。
2. 在 WorkBuddy 打开「专家·技能·连接器 → 技能 → 添加技能 → 上传技能」，选择下载的本地技能包。官方当前说明中，对话安装面向市场技能；自定义包走上传入口，不能假定粘贴任意 GitHub 链接就已安装。导入失败时保留具体报错，不要让模型声称安装成功。[官方技能安装说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)
3. 新建本地任务并选择 Agent 执行模式，启用该技能。将解压的仓库、运行目录和本期输入/输出安排在同一个独立工作空间内；例如工作空间下分别放 `kinetic-tech-video-workflow/`、`kinetic-runtime/` 和 `my-video/`。运行目录必须在技能源码目录之外。
4. 先检查 Python 3.12+、Node 22+、FFmpeg/ffprobe 和 Chrome/Chromium，再实际跑演示。技能导入不会保证这些工具已经安装。命令中的 `python` 应替换为本机真正可运行的 Python，不是 Windows 应用商店占位入口。

WorkBuddy 官方支持 `SKILL.md` 和可执行脚本；其开放平台文档说明脚本经 Bash 工具调用。本项目仍需客户端允许启动本地 Python、Node、FFmpeg 和无头浏览器，纯聊天或未提供命令执行能力的环境无法只凭模型完成渲染。[官方技能结构](https://open.workbuddy.cn/docs/skill)

## 先检查环境，再跑演示

以下命令在解压后的仓库根目录执行。路径只是同一工作空间内的示例，可整体换到合适位置；新的输出目录不能与已有结果重名。

```text
python scripts/runtime.py --work ../kinetic-runtime doctor
python scripts/runtime.py --work ../kinetic-runtime bootstrap
python scripts/make_demo.py --out ../kinetic-demo-input
python scripts/workflow.py validate --work ../kinetic-runtime --job ../kinetic-demo-input/job.json
python scripts/workflow.py run --work ../kinetic-runtime --job ../kinetic-demo-input/job.json --out ../kinetic-demo-output
```

先处理 doctor 报告的缺项，再继续 bootstrap。演示使用生成的几何图与测试音，不是专业配乐、人声识别或创作质量展示。演示通过后，按 `examples/job.example.json` 与本期实际素材准备 `job.json` / `user.json`，再调用相同的 `workflow.py validate` 和 `run`。它会串联模板、封面、混音和检查；不需要模型自己重写视频合成代码。

默认权限下，WorkBuddy 可能针对命令、网络或工作空间外访问要求确认。按提示核对具体动作，不能把暂停等待权限写成执行成功；不必为使用本项目关闭所有安全设置。[官方权限与安全沙箱](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Permission-Modes)

## 可以复制给 WorkBuddy 的提示词

```text
请使用这个仓库的酷炫科技风视频技能，先读取 SKILL.md、README 和 references/workbuddy.md。

先实际运行 runtime.py doctor，报告缺少的工具，再按文档准备运行环境。生成测试 demo 并用 workflow.py validate / run 完整执行，查看检查报告与抽帧。不要把计划、静态预览或命令文本当成已经导出视频。

演示通过后，再根据我提供的原片、真实字幕时间和音乐准备本期 user.json 与 job.json。需要编辑判断的标题、分镜、人物选帧应依据全文；缺失的必要素材要明确指出，不虚构转写结果或授权。

请调用仓库公开脚本，不擅自重写 scripts/ 或 assets/template/，不改用另一套模板。遇到失败，报告失败阶段、错误和日志位置，不绕过校验、不静默省略 BGM 或封面，不把中间的 silent-with-audio.mp4 当完整交付。

最终交付经过检查的 MP4、PNG/JPG 封面、适用的 SRT 和检查记录。说明哪些已经实际验证，哪些还需要我观看或试听。只改封面时沿用既有音乐选择、音量和音轨时间轴。
```

## 本地导入与市场提交的区别

官方本地上传说明没有单独列出市场元数据为本地导入的强制条件；不能据此断言一定需要额外格式转换，也不能把未做的本地导入测试写成已经兼容。当前先使用通用技能包；若实际客户端出现结构或字段错误，再按报错做最小适配。

向 **WorkBuddy 开放平台提交市场技能** 是另一项工作。其文档明确要求 `name`、`display_name`、`display_name_en`、`description`、`description_zh`、`description_en`、顶层 `version`、`author`；用途主要包括市场展示。市场版需要按该规范补元数据并通过平台解析，但这不构成本项目已经上架市场的声明，也不是现在必须生成第二套脚本的理由。[开放平台技能规范](https://open.workbuddy.cn/docs/skill)

## 能保证到哪一步

固定脚本降低了对模型逐步写代码的依赖；相同输入、参数和已验证环境可复现同一套视觉与混音流程。新片的转写准确率、语义分镜、标题、人物选帧和选曲仍需要判断，本项目不附带自动语音识别模型。不同模型、系统和浏览器也可能出现差异，不能保证任意新片都达到相同审美或百分之百一次成功。
