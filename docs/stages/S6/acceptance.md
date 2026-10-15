# S6最终发布验收

状态：**accepted**。最终发布tag为`v1.0.0`，完整验收记录见[reports/s6-acceptance.json](../../../reports/s6-acceptance.json)。独立GitHub候选`52b691f`已通过全部发布核查；验收提交只追加报告与材料状态，不修改GPU执行路径。

| 验收条件 | 实际证据 |
|---|---|
| 干净checkout、脚本与资产获取 | 从独立GitHub仓库fetch候选并建立干净工作目录；新下载OSS aiohttp、归档/成员hash核验，另建CPU环境，39测试无skip，安装包确实指向独立checkout且无torch/vLLM；[远端核查](../../../reports/s6-github-readback/readback.json) |
| 依赖可移植入口 | 本地36wheel硬链接到新目录后验证原hash并重写路径，原GPU锁不变；缺失/错hash拒绝且不生成输出；[本地核查](../../../reports/s6-local-verification/summary.json) |
| 固定实现与原始结果 | 99个受保护执行/数据/配置/锁/测试文件与S5一致；六份S5产物逐字节复算、最终资产索引精确重算；原GPU数据仍绑定原运行SHA |
| 留存与版本 | 5个既有阶段tag核验，654份终态run与182对象收据/文档链接审计通过；新增发布版本不移动旧tag |
| 最终材料 | [README](../../../README.md)、[快速开始](../../quickstart.md)、[复现](../../reproduce.md)、[最终报告](../../final-report.md)、[结果/阶段](../../results-index.md)、[资产](../../assets.md)、[27项覆盖](coverage.md)、[累计讲解](README.md)、[六条简历](resume.md)、[学习核验](../../learning-guide.md) |

GPU侧完整复测由已验收S5覆盖：三轮39计时进程、9216 HTTP、十profile×256最终质量与最后10项GPU/CPU回归。S6没有新增GPU推理、训练或宿主迁移；新版GPU bootstrap仅验证路径处理与帮助入口，不能宣称再次完整重建了GPU环境。S1原锁完整独立重建和S5最终GPU执行证据仍保留。

所有工程与材料交付条件均已通过。高rate自然SLO未充分满足、动态K无稳定额外优势、AWQ×spec负收益、heap成本、CUDA独立范围和历史波动均保留。用户是否已经独立掌握另行核验，当前仍未验证。
