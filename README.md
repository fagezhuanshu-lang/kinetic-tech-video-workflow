# 酷炫科技风完整视频工作流

把口播素材做成横屏科技风视频：真实 MotionGit 模板动效、原声、中文字幕、动作音效、BGM、人物标题封面，以及最终 MP4 检查。

这个项目把已实际运行的流程整理为脚本。它提供固定执行步骤，不要求助手每次重新写渲染器。公开版没有原用户的录像、人物封面、字幕全文、缓存音乐、账号凭据或私人机器路径。

## 能做什么，不能保证什么

输入素材、文案、分镜、字幕时间和配乐选择确定后，脚本负责 plan → prepare → preview → render → cover → mix → verify，并集中交付 MP4、PNG/JPG、SRT 与来源/检查记录。BGM 或封面缺失、实际验收失败时返回错误，不把无配乐中间版本标记为完整交付。

较弱的模型也可以调用这些固定脚本，因此能减少漏步骤和命令拼错。但字幕纠错、语义分镜、标题、选帧与选曲仍需要判断；本项目没有内置 ASR 模型，也不是任意视频的一键完美剪辑器。相同参数在已验证环境中可复现，不等于任意素材、模型、操作系统都达到同样的审美质量。

- 模板规格：1920×1080、60fps、横屏。竖屏原片可作为人物窗素材，不会把成片自动变成竖屏。
- 实际测试平台：Windows x64。macOS/Linux 提供路径发现逻辑，尚未完整实测。
- WorkBuddy：按其公开技能/脚本机制提供使用说明，**尚未在 WorkBuddy 客户端内实测**；[安装与权限说明](references/workbuddy.md)。
- 新电脑须安装系统工具。已验证在全新 Python 虚拟环境中联网安装 Python/Playwright 依赖；系统 Node、FFmpeg、Chrome 仍复用已安装工具，不声称空白操作系统已通过无人值守安装。

## 先跑一个不含私人素材的短样例

需要 Python 3.12+、Node.js 22+、FFmpeg/ffprobe、Chrome 或 Chromium/Edge。Python 依赖由 bootstrap 按 `requirements.txt` 准备；Playwright 按 npm lock 安装。系统程序缺失时会说明，不会假装已经存在。完整说明见 [运行环境](references/runtime.md)。

在解压/克隆后的仓库目录执行，Windows 可使用已安装的 Python 完整路径替代 `python`：

```sh
python scripts/runtime.py doctor
python scripts/runtime.py bootstrap
python scripts/make_demo.py --out ../kinetic-demo-input
python scripts/workflow.py run --job ../kinetic-demo-input/job.json --out ../kinetic-demo-output
```

首次 `doctor` 返回未准备是预期情况；解决其列出的系统缺项，再运行 bootstrap。路径默认是仓库旁的 `.kinetic-tech-runtime`，也可统一传 `--work` 或设置 `KINETIC_RUNTIME_HOME`。不要把不同命令指向不同 runtime。

样例的几何人物与声音均由脚本生成。声音是**合成测试信号，不是自然人声或推荐歌曲**；样例用于验证链路。正式视频请使用自己的口播、真实字幕和许可合适的配乐。

## 制作自己的视频

1. 准备自己的视频/旁白、句级字幕和音乐；先读全文，再选分镜、封面标题与清晰人物帧。
2. 按真实模板 schema 写 `user.json`；读取 [模板创作入口](assets/template/CREATION.md)，不要把场景时长随意拉伸。
3. 复制 [job.example.json](examples/job.example.json)，绑定素材和封面参数。相对路径以对应 JSON 文件为基准。
4. 执行 `python scripts/workflow.py validate --job 你的job.json`，再执行 `run --job ... --out 新输出目录`。
5. 打开最终视频与封面检查内容。机器验收不替代人耳试听、字幕事实核对或发布平台检查。

详细输入字段、恢复与交付位置见 [统一执行入口](references/workflow.md)。音乐默认使用已验证过的归一化、避让与淡入淡出设置，可在 job 中调整；代码不附送商业歌曲。封面独立导出并只替换成片首帧，不延后原声音轨。平台发布时仍需按发布页面选择独立 JPG。

## 给 AI 助手使用

仓库根目录 [SKILL.md](SKILL.md) 是技能入口。可以下载源码 ZIP，在支持本地技能包的客户端导入；也可让具备本地命令执行能力的助手读取本仓库。GitHub 链接本身不能给一个只有聊天能力、无法执行程序的模型增加视频渲染能力。

推荐给学员的提示词：

> 先阅读这个仓库的 SKILL.md，用 doctor 检查环境，再跑自带短样例。通过后，使用我提供的口播、字幕和音乐准备 job.json，通过统一 workflow 入口制作。不要修改渲染代码，不要省略 BGM、封面或最终检查；失败时报告实际错误和已完成阶段。

WorkBuddy 本地导入与市场发布是不同流程。本仓库并未宣称已经上架 WorkBuddy 技能市场，也没有客户端实测认证。

## 开源与素材来源

新增工作流代码以 [MIT](LICENSE) 发布。真实模板来自 [motiontemplates/all](https://github.com/motiontemplates/all) 的 MotionGit #385712 / kinetic-tech 0.2.7-open-beta 公开版，保留原版权和许可证。

字体、品牌素材、第三方软件具有各自条件，见 [第三方声明](THIRD_PARTY_NOTICES.md)。尤其 MotionGit 品牌图形不是本仓库新获得的商标权。你输入的视频、人物、配乐和成片内容不因为使用本代码就自动获得版权许可。

公开版发布清单与本地验证范围见 [发布与验证](references/release.md)。本项目不自动上传素材，也不替你发布视频。
