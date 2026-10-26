# interview-practice 学习迁移核查

核查日期：2026-10-26。目标是让新 clone 能继续同一套概念学习、源码对照与历史结果分析。机器学习进度仍是 **M4 AWQ 通道缩放已理解，裁剪待手算；M3 未开始**，详见[交接记录](learning-handoff-2026-10-26.md)。本次没有运行新的 GPU 实验，也没有将助手核查计为用户完成 R1–R8。

## 与 main 相比，哪些实验已经保留

核查基点：`main=c166c93e1f16262f6f64f5eae31c81494c5a2d1f`；补充前 `interview-practice=3c6651edd64110adf8a36084eade19f7632ea606`。两者的 `reports/`、`experiments/`、`data/`、`configs/`、`patches/`、项目源码和依赖锁的 Git tree 完全相同。原有实验没有被删除或改写；新增内容单独列出。

| 工程阶段 | 已跟踪运行数 | 学习入口 |
|---|---:|---|
| S1 准备与基础核验 | 66 | [阶段记录](../stages/S1/README.md) |
| S2 六条主线首轮实现与验证 | 181 | [累计讲解](../stages/S2/README.md)、[回放](../stages/S2/replay.md) |
| S3 稳定性与边界 | 167 | [累计讲解](../stages/S3/README.md)、[结果](../s3-stability.md) |
| S4 深化与代价 | 69 | [累计讲解](../stages/S4/README.md)、[结果](../s4-depth-results.md) |
| S5 组合、真实负载与最终质量 | 167 | [累计讲解](../stages/S5/README.md)、[结果](../s5-results.md) |
| S6 发布、证据与复现 | 4 | [累计讲解](../stages/S6/README.md)、[最终报告](../final-report.md) |

合计 **654 个 run、3,749 个运行文件、264 个报告文件**。其中 613 个 run 为 completed、28 个 failed、13 个 interrupted；这些是记录条数，不能全部描述为成功实验。S1–S6 是工程阶段，M1–M6 是技术主线，不一一对应。

`.gitignore` 忽略 `experiments/runs/` 与 `artifacts/` 的新输出，但不影响已经显式纳入 Git 的历史文件。普通未跟踪文件在本次开始核查时为 0；缺口主要来自被忽略的文件。详细数量、tree ID 和补充文件 SHA256 见[机器可读清单](portability-inventory-2026-10-26.json)。

## 这次补充了什么

| 本机原有资料 | 迁移处理 |
|---|---|
| `artifacts/interview-prep/` 的最低指南、R1–R8、进阶附录、源码对照及版本记录 | 迁入本目录，修订旧的“不提交”、固定项目路径和创建分支说明；入口见 [README](README.md) |
| 本机旧版学习材料、S3–S6 讲解草稿 | 28 个原文件完整保存在[历史归档](assets/historical-learning-materials.tar.gz)，附[逐文件清单](assets/historical-learning-manifest.json)；包含已被正式文档取代的草稿，不作为当前执行指令 |
| `third_party/` 中的固定 vLLM 与 nano-vLLM | 两份源码包及原始许可证随 Git 保存，离线恢复到原源码阅读路径；vLLM 原归档与 `configs/upstream.json` 的 SHA256 一致，2,378 个文件均逐字节核对 |
| Nsight `engine-observers-v1.sqlite` | 在原路径显式纳入 Git，SHA256 与既有 `reports/s2-nsight-engine.json` 一致；原 `.nsys-rep` 和 CSV 本来已跟踪，可直接 CPU 复算 |
| 2026-10-25 服务启动检查 | 保留 [run manifest](../../experiments/runs/20261025T105219+0800-f94171f629/manifest.json)、日志、环境及[请求核验](../../artifacts/maintenance/disk-cleanup-20261025/startup-verification.json)、普通/流式响应。是清理后的两次开发请求，主动停服导致 interrupted，不是性能基准或新的阶段验收 |
| `artifacts/learning/` | 仅发现前次交接的 GitHub 读回收据，未发现用户实操笔记；学习进度已保存在交接文件，后续个人笔记请提交到 `docs/interview-prep/notes/` |

新增服务记录后，当前分支共有 **655 个 run**；原发布口径仍为 654。原 manifest、输出、状态和源码 SHA 保持不变。

## 哪些忽略文件不需要直接纳入 Git

- **模型、教师状态、校准资产、环境快照、wheels、工具和容器**：沿用[资产索引](../../reports/release-assets.json)、[资产说明](../assets.md)及[容器恢复](../container-recovery.md)中的固定收据和校验方式。Git 保存入口与证据，不把这些运行资产全部复制进学习分支。本次没有重新从 OSS 下载或核验大资产的当前远端可用性。
- **虚拟环境、`__pycache__`、build、包缓存**：按锁文件重建；把旧环境直接提交不能保证跨机器运行。
- **`artifacts/reports/`、各轮 `state.json`、调度日志和备份中间文件**：部分报告与 `reports/` 完全相同，其余是阶段中间版本或恢复工作文件。正式结果、raw run 和最终状态已跟踪；既有原始证据通过全量哈希审计确认，历史讲解草稿另行保留。
- **network、OSS 工作目录、磁盘清理细目、过期 handoff**：属于本机运维状态，不作为新机器启动状态；不整体提交，避免把旧进程、路径和连接状态当成可复用配置。与学习有关的最近服务核验单独保留。
- **`artifacts/upstream-audit/` 中的 FlashInfer wheel 源码**：属于旧环境兼容性排查参考，未被当前学习路线用作源码入口；固定包版本/哈希见依赖锁与 wheel 收据，恢复依赖时再获取。

忽略项没有被删除。原始材料的“未验收”“尚在运行”等状态只描述历史时点，当前状态以正式阶段文档为准。

## 新机器怎样获得同一套学习入口

已 clone 且本地已有学习分支时，在项目根目录执行：

```bash
git status --short --branch
# 有未提交工作时先保存；有本地分叉时下面的 --ff-only 会停止。
git fetch origin interview-practice:refs/remotes/origin/interview-practice
git switch interview-practice
git merge --ff-only origin/interview-practice
python3 scripts/restore_learning_sources.py
python3 scripts/restore_learning_sources.py --check
```

若本地尚无该分支，把 `git switch interview-practice` 改成 `git switch --track origin/interview-practice`。脚本只用 Python 3.11+ 标准库，读取随仓库保存的源码包，无需联网、GPU、pip 或 OSS 权限；已有同内容文件会跳过，有不同内容会报错并保留修改。恢复的是源码，不含上游 `.git`，也不自动安装任何框架。

然后从本目录 [README](README.md) 接续学习。概念讲解、源码对照、保存的性能/质量结果、Nsight 时间线和 CPU 结果复算都具备资料。实际启动服务、训练、量化或重新测性能仍需恢复运行环境与相应模型，并核验新宿主 GPU；不承诺单凭 Git clone 即可跑完整 GPU 实验。

仅用 CPU 复算 Nsight 报告的示例（不改变原报告）：

```bash
python3 scripts/analyze_nsys.py \
  --sqlite artifacts/profiles/engine-observers-v1.sqlite \
  --nsys-rep artifacts/profiles/engine-observers-v1.nsys-rep \
  --report artifacts/learning/nsight-recomputed.json
```

S5 六份结果精确复算及完整证据核查的入口见[复现说明](../reproduce.md)。若使用浅克隆，完整历史 SHA 审计前需 `git fetch --unshallow origin`；读取报告与恢复参考源码不依赖完整历史。

## 本次验证记录

对暂存候选快照执行了 `git clone --no-local`，新检出中没有本机的虚拟环境、模型、`third_party/` 或未跟踪学习文件。实际验证通过：

- 离线恢复及 SHA256 核对 2,378 个源码文件；重复运行不改文件；发现已有修改时，保持修改和缺失文件的原状态，不先写入其他文件。
- 检查当时本目录 170 个 Markdown 本地链接，均能解析；28 个历史材料原文和 10 个补充证据文件哈希全部一致。
- 使用 `audit_evidence.py --through-stage S6 --require-tracked` 核对 655 个 run 的原始资产、源码提交和保存的 OSS 收据，全部通过。
- 使用原始输出重新生成 S5 的 composition、openloop、final-quality、final-gpu、结果表、资产读回报告，以及 S2 Nsight 报告；**7 份产物均与原文件逐字节相同**。这是 CPU 分析，不是重新执行 GPU 实验。
- 完成复算后，该检出仍无已跟踪文件变更。

实际命令、退出码、日志及证据审计见[验证记录](../../reports/learning-portability-20261026/validation.json)。其中候选 SHA/tree 描述本地暂存验证时点，验证后只补充本节、笔记入口和验证记录；正式提交与远端读回另由 Git 记录。原始 SSE、服务日志的空白和回车保留不变，以维持历史哈希。
