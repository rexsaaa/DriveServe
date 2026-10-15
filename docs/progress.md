# DriveServe 当前进度

**S1–S6全部accepted。最终版本v1.0.0。** 持续目标的工程实现、实验、资产留存、累计讲解和发布核查均已完成；用户独立掌握尚未核验。

## 验收与证据

| 阶段 | 已验收版本 | 证据 |
|---|---|---|
| S1准备 | stage-1-foundation | 原模型/服务冒烟、固定环境独立重建、完整OSS读回 |
| S2六线基础 | stage-2-minimum | 27项最低要求，真实引擎修改、128步训练、三组AWQ、CUDA/FA2/Nsight/部署 |
| S3完善 | stage-3-validated | 三轮54进程与16项边界，414run审计及远端复算 |
| S4深化 | stage-4-depth | heap与CUDA两个专题，三轮24进程，483run审计及远端复算 |
| S5组合 | stage-5-release-candidate | 三轮39进程、9216HTTP、10×256最终质量、最后10项回归、650run审计 |
| S6发布 | v1.0.0 | 独立GitHub候选52b691f，全新CPU39测试、六份S5产物/资产索引精确复算、654run审计、99个保护文件不变、5个旧tag核验 |

阶段commit和获取方法见[结果索引](results-index.md)。S5验收reports/s5-acceptance.json及远端标签读回已保存；S6验收reports/s6-acceptance.json与reports/s6-github-readback保存实际证据，最终tag发布后另记读回，不移动旧tag。

## 主要结果与边界

冻结最终test十profile各256完成/JSON有效、236正确。四spec与同Target256条token/结束一致；scheduler/both各2条JSON空白差异，解析/字段/错误ID集合相同。test没有用于调参。

原生APC下FP16 Target/fixed/adaptive三轮总wave15.3711±0.0978/13.3646±0.5854/13.1051±0.2269s，推测首字延迟增加，动态K没有稳定额外收益。AWQ Target9.7624±0.1480s，对fixed16.3439±0.5716/adaptive16.5718±1.0062s，组合默认关闭。自然业务自研cache无额外复用；heap小池默认关闭，独立CUDA未接服务。

HTTP9216/9216完成不代表实时达标：自然高rate三部署均有大量请求未满足SLO；自然每cell242/256正确、填充204/256。P99仅每cell256×3探索性统计，S3 TP2波动原因仍未知。完整条件见[最终报告](final-report.md)、[三轮表](s5-results.md)和[兼容矩阵](s5-compatibility.md)。

## 环境与资产

两RTX4090各49140MiB，driver550.163.01，无NVLink/P2P失败；torch2.6.0+cu124/vLLM0.8.5/transformers4.51.3，原GPU环境/hy-tmp/driveserve/venv-rebuilt。/hy-netdisk实际overlay，GitHub和OSS承担留存。182对象53,125,961,275bytes完整读回，约0.510009元/天，不含用户已有镜像及其他费用；旧30GB上限已取消。资产索引reports/release-assets.json，当前对象/小恢复与历史全量读回范围分开。

S6同机新CPU环境与独立GitHub新CPU环境均通过完整39测试，无torch/vLLM；36基础wheel路径迁移、原hash核验和缺失/错hash拒绝已实测。其他117条索引依赖仍需包索引。未执行实际宿主迁移、物理24GB或S6再次完整GPU重建；GPU执行代码99个受保护文件与S5一致。

GPU实验、上传及核查任务均已结束。机器按用户现有约定保持开机；没有后台定时同步、自动开机或agent自动唤醒。不改Codex认证/隧道/tmux，不依赖Mac。新增其他付费资源或后续范围变化仍需用户决定。

## 学习与后续使用

从[快速开始](quickstart.md)、[复现](reproduce.md)、[累计六线讲解](stages/S6/README.md)、[六条事实简历](stages/S6/resume.md)进入。[学习核验表](learning-guide.md)六线全部待用户实际复述与追问验证；材料完成不等于已经掌握。后续可选研究不属于本次未完成事项。早期过程保留于[历史进度](progress-through-s5-development.md)和各阶段tag。
