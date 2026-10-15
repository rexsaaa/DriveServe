# 结果与阶段版本索引

所有数字从原始run经版本化脚本产生；run manifest记录源码SHA、环境、模型/数据/配置与文件hash。重测会产生新run，新环境不得沿用旧baseline计算收益。

| 主题 | 原始重聚合/验收 | 解释与入口 |
|---|---|---|
| 六线基础闭环 | [S2验收](../reports/s2-acceptance.json) | [S2累计讲解](stages/S2/README.md) |
| 重复与边界 | [S3主表](../reports/s3-stability.json)、[边界](../reports/s3-boundaries.json) | [S3稳定性](s3-stability.md) |
| heap与CUDA深化 | [S4主表](../reports/s4-depth.json)、[维护诊断](../reports/s4-heap-maintenance.json) | [三轮表](s4-depth-results.md) |
| 组合与开环 | [组合](../reports/s5-composition.json)、[HTTP](../reports/s5-openloop.json) | [S5主表](s5-results.md)、[结论](s5-discussion.md) |
| 最终test256 | [十profile质量](../reports/s5-final-quality.json) | [冻结协议](../configs/s5-final-quality.json)、[兼容范围](s5-compatibility.md) |
| GPU最后回归 | [十项回归](../reports/s5-final-gpu.json) | [S5验收](stages/S5/acceptance.md) |
| 资产与远端复算 | [182对象/10小恢复](../reports/s5-assets.json)、[39CPU/六产物精确复算](../reports/s5-github-readback/readback.json) | [资产索引](assets.md)、[复现](reproduce.md) |

## 可获取阶段

| 阶段 | tag | 已验收commit |
|---|---|---|
| S1 | `stage-1-foundation` | `0e149614385a72ef1fefe62a860d49c94ad29127` |
| S2 | `stage-2-minimum` | `5dc0a8e5b608a850fd24573ae6923761b33d1c44` |
| S3 | `stage-3-validated` | `96bde7bd283b0f6b320c2f9220c709c09bc7c032` |
| S4 | `stage-4-depth` | `21fbdf7d429300c617d019bff0f09b3dc72cb199` |
| S5 | `stage-5-release-candidate` | `df805a54d0d1c869ef8188a2c142205bd366a8fe` |
| S6 | `v1.0.0` | 用`git rev-parse v1.0.0^{}`解析最终验收commit |

```bash
git fetch origin --tags
git switch --detach stage-5-release-candidate
```

旧阶段各自tag包含当时完整代码与证据；不要将旧聚合器与新版报告混用。最终S6新工具已通过独立GitHub核查，完整证据见[验收](stages/S6/acceptance.md)。
