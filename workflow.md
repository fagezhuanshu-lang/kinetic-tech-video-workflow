# 单一执行入口

`scripts/workflow.py` 将原生 plan、prepare、preview、render、封面、最终混音与编码、实际成片验证和交付收集固定为一个流程。它不自动写口播、不自带 ASR、不替用户判断文案与素材许可。模型负责形成正确的输入文件，程序负责执行和检查。

## 准备输入

1. 按 `assets/template/params.schema.json` 和 `CREATION.md` 编写本期 `user.json`。真人原声通过 `media.voice.mode=file` 绑定；字幕用实际提供/测得的 `captions`，不能省略或编造逐字时间。原生动作音效设置为 `native`。
2. 复制 `examples/job.example.json` 为本期 `job.json`。`user_input`、`music.file`、`cover.frame` 的相对路径均以 job 文件位置为基准；user.json 里的媒体路径以 user.json 所在目录为基准。job 示例是字段示意，不附带用户音乐或视频，需绑定自己的文件。
3. 封面人物选择三选一：`frame_time` 是原片/prepare 输出时钟上的秒数，要求 presenter 为视频；`frame` 是外部图片路径；`instance_frame` 是准备好实例内部的相对图片路径。标题、标签、副标题和页脚按本期内容编写。程序不会替你判断表情是否自然。
4. `music.start` 是音乐截取起点，默认为 0；选段必须覆盖全部片长。已知曲名、真实来源和许可记录可填 `name/source/license`，未知时不伪造。`mix` 可覆盖已认可的音量与淡入淡出默认值。

job 的未知字段、错误类型和互斥封面选项均会报错，完整定义在 `schemas/job.schema.json`。

## 执行

先按 [runtime.md](runtime.md) 准备 Python、Node、FFmpeg 和 Chrome 及 runtime。通过以下单一入口运行：

```powershell
python scripts/workflow.py validate --job /path/to/job.json --work /path/to/runtime
python scripts/workflow.py run --job /path/to/job.json --out /path/to/new-video --work /path/to/runtime
```

`--work` 默认读取 `KINETIC_RUNTIME_HOME`，否则是仓库上一级的 `.kinetic-tech-runtime`。需要先准备依赖时可加 `--bootstrap`；系统工具必须已存在或由 runtime 的显式参数配置。入口本身只依赖 Python 标准库，schema 校验与制作使用 runtime 中锁定依赖的 Python。命令中的路径是占位，替换为自己的位置；不要直接照抄到一个不存在的盘符。

`validate` 只检查 job/native JSON schema 与输入文件存在和哈希，不代表素材时长、原生编排、渲染或成片通过。`run` 会继续做这些实测检查。原生中间渲染的 BGM 设为 none，最终由 finish 阶段按 job 音乐与混音参数统一合成；中间文件不能作为完整交付。

## 状态、失败与交付

输出目录必须不存在。每个阶段写入 `workflow-state.json`，详细输出在 `logs/`。失败返回非零退出码，状态不会标 complete。当前入口不自动从半成品恢复；先查看日志修正问题，再使用新的 `--out`，原输出保留。熟悉下层接口的人可以单独复用已完成的实例/封面，但不能将未验证阶段冒充完成。

成功后只从 `delivery/` 交付：`completed.mp4`、PNG/JPG 封面、`captions.srt`、封面/音乐来源、输入哈希、自动验收记录和 `delivery-manifest.json`。SRT 只转换原有句级时间，不重新估算。首帧封面不改变正文/音频时间轴，也不自动设置发布平台封面。

自动检查成功后，仍应实际看封面和 `qa/contact.jpg`，播放最终视频确认内容与听感。程序不会把波形检查称为人耳试听，也不能证明任意模型在任意电脑都能获得相同创作质量。
