# DriveServe 当前进度

更新：2026-10-15T13:04:26.498277+08:00。**S1/S2 accepted；S3 in_progress；S4–S6未验收。** 最近完整版本stage-2-minimum指向5dc0a8e，GitHub tag已读回。六线27/27最低要求validated，不代表S3独立重复或后续深化完成。当前无预算、凭据或范围选择需要用户处理。

## 当前真实任务与下一步

S3第二轮18/18已完成，第一轮也18/18，共36个独立进程。从两轮原始记录重算39指标组，reports/s3-r12-stability.json与docs/s3-stability.md保留逐run、均值/标准差。全部推测每轮137条token与Target一致；业务121/128。三部署累计1536/1536成功，TP2长填充仍dev-030差异，两轮所有并发均同样复现。动态K相对trained fixed的耗时差第一轮略好、第二轮变差，不能宣称稳定增量加速。GPU已释放，无OSS任务。

下一步先运行新提交的scripts/probe_rope_index_alias.py。源码复查发现positions/slots可能与projection/cache共享存储，现有checked wrapper只检查三个浮点张量之间别名；探针用真实CUDA view但拦截extension，不发危险kernel。尚未实测前只记边界疑点。正常输入和CUDA内核未修改，第三轮继续相同执行源码，全部重复结束后再修补和补齐正常/非法输入回归。

随后入口：`python3 scripts/run_experiment_plan.py --plan configs/s3-timing-plan-r3.json --state artifacts/s3-timing-r3/state.json`。状态记录进程指纹和任务，不重复启动；Git在本轮保持干净，不另起GPU或OSS工作。失败检查后整单元重测，不拼接性能。第二轮state已封存reports/s3-timing-r2-state.json，新增温度/功耗/频率前后快照；不是连续遥测。

全部三轮完成后补configs/s3-boundary-plan.json，现13项诊断：原9项加original/trained fixed各2次独立trace（与S3已有Graph诊断形成3次接受率观测）。fixed-K正式计时不启用观察器，因此不能从缺失接受计数填0或推定接受率；诊断时间不进入性能主表。另需将索引alias修复后的contract及48数值加入回归。

临时准备稿位于artifacts/preparation-s3-s4和/tmp/driveserve-*，尚未集成/验收；包括S3累计讲解/回放、alias修复候选和S4堆索引/CUDAhead tile设计。S4须S3验收后根据完整实测选题；不把草稿或参数扫当深化完成。

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
