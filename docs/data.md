# 代理任务、冻结数据与用途隔离

DriveServe研究结构化文本代理任务，不是实车感知—规划—控制或驾驶安全验证。输入包括车速、限速、前车距离、信号灯、行人、封闭车道和能见度；输出action、speed_band、must_yield。单位m、m/s。规则是项目自建的stop→slow→proceed优先级，限速仅作上下文，不提供可执行车辆控制。

`driveserve/task.py::validate_scene`拒绝缺字段/额外字段、非有限数和越界数，布尔不接受0/1替代。`label`是独立规则oracle，教师输出不是唯一真值。`score`只接收一个严格JSON对象，拒绝重复键、缺失/额外字段、NaN、错误类型及Markdown包装，报告JSON有效、三字段准确和全字段匹配。rule-oracle demo只验接口，不能作为模型成绩。

## 当前冻结资源

| 用途 | 实际资源 | 隔离和限制 |
|---|---|---|
| 教师蒸馏 | frozen-v1 train512；7B生成后472合格/40排除，实际128步LoRA | 仅train梯度；teacher/dev121条合格子集仅验证答案loss；模型业务质量在完整dev128测 |
| AWQ领域校准 | frozen-v1 calibration256中的固定来源，32×512=16384tokens | 来源scene ID与token文件hash固定，不用dev/test |
| AWQ通用校准 | WikiText2 train，revision b08601e04326c79dfdd32d625aee71d232d685c3，同16384tokens | 保留CC-BY-SA-3.0/GFDL许可与Wikipedia/WikiText署名；原文/token衍生物按来源约束使用 |
| 开发质量 | frozen-v1 dev128，独立规则标签 | 用于选择与质量门槛；与性能合成压力单列 |
| 最终质量 | frozen-v1 test256 | S5前不送模型、不用于训练/校准/调参；生成时做划分审计不等于模型评测 |
| 性能/机制 | 固定barrier、热点/一次性混合、长短输入、长输出、EOS/长度/上下文边界；HTTP512/1536填充 | 每run保存实际token/输入hash和配置；合成长填充显著降质，不能推广真实道路 |
| 算子 | 固定seed张量与形状 | 独立数值/Event/内存检查，不替代任务质量 |

frozen-v1使用seed2026101501，共1152条/288场景组，每组四变体；train128组、calibration64组、dev32组、test64组。冻结时检查scene ID、group和精确内容跨split无重复，与旧fixture无重叠。规则、系统模板跨split共享，连续特征也可能接近，所以不宣称跨任务、未见模板或真实道路泛化。

`data/frozen-v1/manifest.json`保留生成代码SHA、各split hash、数量、组数、标签分布和prompt hash。正式对照不静默替换数据或评分规则；任何更改须新版本和受影响回归。`data/samples/proxy-v1.jsonl`是旧128条开发fixture，各split32；其test名称不代表最终test。

教师640条来自train/dev，逐条保留prompt/output token、独立评分、finish和过滤原因。训练保存每optimizer步的sample_ids、只对答案含EOS计算loss；完整checkpoint含优化器/scheduler/RNG/order/cursor。S3审计入口`audit_data_isolation.py`核对保留teacher、四份训练轨迹与AWQ来源，不打开最终test内容。审计结果状态以相应run为准，不能以脚本存在当通过。

数据生成规则、独立评分和任务schema是项目贡献；WikiText、原始模型、AutoAWQ等来源单独署名。项目自建规则记录没有外部数据集内容；原始模型许可不因本项目而改变。原始产物保存在Git或有完整读回收据的OSS中，具体入口见[恢复说明](reproduce.md)和[存储](storage.md)。
