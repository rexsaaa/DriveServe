# 面试学习交接入口

本目录保存可随 Git 克隆迁移的个人学习资料。它记录学习进度，不改变 S1–S6 的工程验收状态。

**截至 2026-10-26（Asia/Shanghai），当前学习停在 M4：已经用数值例子理解 AWQ 校准与通道缩放，裁剪尚未手算演示；M3 尚未开始。**

## 新助手阅读顺序

1. [学习进度与对话交接](learning-handoff-2026-10-26.md)：先看当前位置、用户实际回答、纠正内容和下一步。
2. [学习方案原文快照](interview-prep-driveserve_claude.md)：保留六条主线的完整历史提纲与教学约定。正文含已发现的错误，按交接记录及源码、报告纠正，不直接背原文。
3. 交接文件各主线中的源码、报告链接：需要深入或复核时再打开，不重新扫描全部仓库或自动运行实验。

[快照清单](snapshot-manifest.json)记录原方案路径、SHA256、字节数和交接前的代码版本。原文件 `artifacts/interview-prep/interview-prep-driveserve_claude.md` 被 Git 忽略；本目录中的快照才随本次提交迁移。

## 新机器获取

本次交接保存在 `interview-practice` 分支。普通 clone 默认检出 `main`，请明确指定学习分支：

```bash
git clone --branch interview-practice --single-branch --depth 1 https://github.com/rexsaaa/DriveServe.git
cd DriveServe
git status --short --branch
git log -1 --oneline
```

如果新机器已经克隆了仓库，先确认没有需要保留的未提交修改，再获取并切换学习分支：

```bash
git fetch origin interview-practice:refs/remotes/origin/interview-practice
git switch --track origin/interview-practice
```

若本地已经有该分支，改用 `git switch interview-practice`，再检查与远端差异，不覆盖已有工作。

原历史路径不是接续学习的必要条件；在新仓库中直接使用本目录即可。不要盲目覆盖新机器上已有的 `artifacts/interview-prep/` 文件。

克隆源码和这些交接文档，可以继续概念学习。模型、Python 环境、CUDA、OSS 权限和被忽略的其他个人资料不会因这份交接自动恢复；要实际运行实验时，再读[容器恢复](../container-recovery.md)、[资产说明](../assets.md)并核验新机器。仅继续讲解，不需要先启动 GPU 服务。

## 复制到新会话的提示词

```text
我正在按 DriveServe 的面试学习方案继续学习。请先阅读：
1. docs/interview-prep/README.md
2. docs/interview-prep/learning-handoff-2026-10-26.md
3. docs/interview-prep/interview-prep-driveserve_claude.md 的学习策略部分

学习顺序是 M1 → M5 → M6 → M2 → M4 → M3。
当前停在 M4：我已通过 y=0.13*x1+x2 的例子理解校准数据、
通道缩放与输入反向补偿，以及缩放后再量化为何能降低输出误差。
上次刚纠正：不是降低重要通道原本的贡献，而是降低量化误差对输出的影响；
同一量化组共用量化步长，通道缩放 s 和量化步长 Δ 要区分。
裁剪目前只解释过概念，没有手算例子；M3 尚未开始。

请从一个小型数值例子讲裁剪的作用与代价，再按我的反馈决定是否进入 M3。
优先背景→问题→改动→实测与代价，必要时给小表或手算例子；一次检验一个点。
不要从 M1 重讲，不要把方案中的勾选当成我已掌握，也不要自动重跑实验。
历史方案有已知错误，以交接记录和实际源码/报告为准。
```

这段提示词与交接文档用于恢复教学上下文；Git clone 不会自动迁移聊天应用中的原始会话。
