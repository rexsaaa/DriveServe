# DriveServe 当前进度

更新：2026-10-15T12:19:33.714522+08:00。**S1/S2 accepted；S3 in_progress；S4–S6未验收。** 最近完整版本stage-2-minimum指向5dc0a8e，GitHub tag已读回。六线27/27最低要求validated，不代表S3独立重复或后续深化完成。当前无预算、凭据或范围选择需要用户处理。

## 当前真实任务与下一步

S3首批诊断和独立AWQ重校准均结束，目前GPU空闲、无OSS任务。即将按configs/s3-timing-plan-r1.json启动第一轮18任务；状态文件artifacts/s3-timing-r1/state.json记录runner/包装器进程指纹、每项开始/结束、内层manifest及错误。源码在一轮期间冻结；不要提交文件或启动其他GPU/备份任务使下一项失去可比性。恢复先核验state、manifest、PID/boot/start_ticks和nvidia-smi，不重复已在跑的实验。

入口：`python3 scripts/run_experiment_plan.py --plan configs/s3-timing-plan-r1.json --state artifacts/s3-timing-r1/state.json`。失败停下检查，修复涉及代码需新state保留旧run；未改代码且确认可重测时用--retry-failed。已完成项重校验hash后跳过，不拼接中断计时。当前已有真实CPU失败→重试→跳过演练证据s3-plan-recovery.json。

每轮固定4策略+native trace、4推测配置（Target兼作M4 FP16基线）、3AWQ+Marlin、CUDA、FA2、3部署；共18任务。三轮顺序循环移位，逐run报告均值/标准差/范围，P99仍是64/cell的小样本探索。各轮结束后聚合、记录和提交再进入下一轮。第一次analyze_replication.py实际运行仍待r1完成，不能据语法检查验收聚合功能。

## S3已完成证据

- 20类CUDA非法输入拒绝且未改存储；负slot不写cache（115852-8c22e153b0）。原CUDA支持范围未扩大。
- Graph四配置137请求各完成，原fixed/新fixed/新adaptive均与Target137/137 token一致，业务121/128；动态K2/3/4、5次变更，s3-graph-boundaries.json。eager历史136/137不删，编译模式改变不自动成为普遍正确性保证。
- domain128重复校准内115848-1eee776d86、父115831-43c009e5ac已完成。13文件/21局部误差与原组精确相同，报告s3-awq-reproducibility.json映射原OSS对象；新provenance在该run/export.json，未重复上传权重。临时复测模型仍在artifacts/models/awq-domain-g128-s3-repeat1。
- 原生AWQ的领域128/通用128/领域64与Marlin128 Graph诊断各137完成，正确121/118/121/121。s3-quant-graph-diagnostic.json中timing_eligible均false（当时GPU1校准），selection pending只表示诊断未重选。原生与Marlin的long-1输出差异保留。
- TP2诊断single121347-2c3c4b695a、tp2 121450-8d1823d041。dev-030同前缀第4token，单卡stop相对pro高0.03125，TP2并列；共同前缀单步Prefill为0.015625/并列。支持并行FP16计算下近似/并列解释，不隔离NCCL单独原因，不抹去质量退化。真实404/400/400失败及后续有效请求已验证。

## S2可回放基础与数据

S2报告s2-acceptance.json，247份终态run hash及Git包含、144对象51,794,986,555bytes完整OSS读回、独立GitHub checkout24项CPU回归与4份核心报告精确重聚合均通过。累计讲解/简历/六线回放在docs/stages/S2。M1真实插桩/Nsight；M2冷热/长度策略与生命周期/B1；M3运行时K/实际128步LoRA/全状态SIGTERM恢复；M4三组AWQ；M5独立CUDA；M6FA2/三部署对照。S2只是最小完整版本，无稳定总体加速或SLO声明。

train512/calibration256/dev128/final-test256分离，final-test未送模型/调参。教师472合格train、40排除，dev121/128；128步训练已完成，不重复训练冒充进度。S3质量阈值为完整dev JSON有效且正确数至少同FP16少1条（本次至少120），是小集合工程门槛，不是安全/统计非劣效保证。默认FP16 Target，实验优化仍分profile保留。

## 环境、资源和留存

两RTX4090各49140MiB、driver550.163.01、无NVLink/P2P失败，TP2 custom all-reduce关。固定torch2.6.0+cu124/vLLM0.8.5/transformers4.51.3，上游ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d，153基础依赖；原wheel不变，使用独立overlay。GPU Python /hy-tmp/driveserve/venv-rebuilt/bin/python；training-deps-v1、awq-deps-v2附加层。Target/Draft/domain128在/hy-tmp模型目录，general128/domain64/repeat128在项目artifacts/models。

/hy-netdisk为overlay，GitHub+OSS负责留存；当前未证明真实宿主迁移或物理24GB卡。OSS约51.795GB、0.49723元/天，不含用户镜像，30GB旧上限已取消。AWQ重复文件精确相同，复用已回读对象，不增加重复云存储。本地新增重复模型5.58GB，后续有空间压力才在核验后回收项目副本；不要删除唯一文件或既有云资产。GPU按量开机无截止日，新增其他付费资源需用户决定。

后续顺序：完成S3独立重复/关键边界和累计验收；依据实测选择S4至少两个实质深化点；S5组合与final-test；S6最终干净checkout/发布。S2验收不结束持续目标。没有自动开机或agent唤醒；用户材料已生成，尚未复述/追问验证。
