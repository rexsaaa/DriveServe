# DriveServe 当前进度

更新：2026-10-15T13:27:25.738074+08:00。**S1/S2 accepted；S3 in_progress；S4–S6未验收。** 最近完整版本stage-2-minimum指向5dc0a8e，GitHub tag已读回。六线27/27最低要求validated，不代表S3独立重复或后续深化完成。当前无预算、凭据或范围选择需要用户处理。

## 当前真实任务与下一步

S3三轮全部18/18完成，共54个独立进程；reports/s3-timing-r1/r2/r3-state.json封存任务映射。从原始记录重聚合reports/s3-stability.json共39指标组，docs/s3-stability.md由脚本生成；代码分别88ed620/e3a133f/ab8f4ce，执行源/配置/输入/硬件核验相同。推测每轮137/137 token与Target相同，质量121/128；三部署累计2304/2304成功，TP2长填充dev-030差异每轮重现。trained fixed总时间14.9691±0.1429s、Target17.1860±0.0277s、trained adaptive15.1730±0.2435s（样本标准差）；动态K无稳定增量优势。所有P99仍是64/cell探索性观察。

alias修补前探针内run20261015T130427+0800-e78bf72ca5、包装器130426-802d73f1b4：4类positions/slots与projection/cache共享存储均到达extension dispatch。探针拦截调用，没有发危险kernel，也没有观察到实际OOB或模型损坏。现在Python公开入口reject_write_aliases拒绝可写张量与任一其他输入共享存储，仍允许只读indices互相共享；CUDA .cu/.cpp未改。新contract扩至24拒绝用例及只读alias正例，正常48数值和16 memcheck都待新run回归。正式计时调用的是事先验证的raw kernel，此修补不能算性能提升。

下一步固定提交后启动16项诊断：`python3 scripts/run_experiment_plan.py --plan configs/s3-boundary-plan.json --state artifacts/s3-boundaries/state.json`。计划包含28CPU检查、数据隔离、真实allocator、Graph生命周期native/both、维护trace、修补后alias探针/contract24/完整48/memcheck16、随机Graph2组及原/新fixed各2次trace。已有S3 Graph诊断与新fixed trace形成3次接受率观测，诊断时间不纳入正式性能。

诊断期间保持Git源码干净，不另起GPU/OSS工作；state与进程指纹为准，不重复仍活着的任务。全部成功后用scripts/analyze_s3_boundaries.py重聚合，脚本当前仅语法检查和旧生命周期字段核对，尚未在本计划结果实际运行。完成累计材料、27项矩阵、资产/远端读回审计后才能接受S3；当前依旧in_progress。

临时准备稿位于artifacts/preparation-s3-s4，index.json列hash，均未等同已实现验证。S4候选为精确语义的堆索引与CUDAhead tile/half2，另有S5开环客户端草稿；不得因草稿存在跳过S3验收或宣称收益。最终test未送模型。当前GPU空闲、无OSS任务，下一项为boundary计划。

## S3第一轮完成与下一步（2026-10-15 12:40）

第一轮18/18任务完成、无失败，代码88ed620。reports/s3-timing-r1-state.json固定任务/进程/run映射，reports/s3-r1-stability.json逐原始文件重聚合39指标组，docs/s3-stability.md由render_stability.py生成。推测137/137逐token相同、业务121/128；三组AWQ正确118/121/121、Marlin121。三部署768/768成功；长填充TP2仍43/64对单卡/副本44/64，dev-030差异保留。只有一轮，所有时间为临时观察。

聚合器真实运行发现的绝对路径/返回tuple接入问题已修复，没有改引擎/CUDA/计时脚本；新增跨run源码/配置/输入hash检查、配对指标和脚本hash。客户端新增4项本地真实HTTP协议fixture，连同原检查28项CPU通过（s3-cpu-precommit.log），不冒充模型输出证据。S3新增数据隔离审计和边界计划，尚待固定代码后运行。任务包装器第二轮起补GPU温度/功耗/频率前后快照；第一轮未采集这一项，不能补造历史遥测。

下一步：提交本单元后启动r2，入口 `python3 scripts/run_experiment_plan.py --plan configs/s3-timing-plan-r2.json --state artifacts/s3-timing-r2/state.json`；本轮保持Git干净，结束后聚合/留存再r3。然后configs/s3-boundary-plan.json补Graph生命周期/维护开销、独立memcheck、随机Graph与数据审计。不得在r2/r3期间另起GPU/OSS任务或修改源码。S3未验收，S4没有实施；最终test未送模型。

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
