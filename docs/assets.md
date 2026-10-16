# 数据、模型与环境资产

完整机器可读索引为[release-assets.json](../reports/release-assets.json)，由scripts/index_release_assets.py从已验证收据与锁文件生成。以下是项目资产，不含用户已有镜像。

| 内容 | 完整读回收据 | 对象数 | 归档字节 |
|---|---|---:|---:|
| 原Target/Draft、对齐Draft和上游AWQ冒烟模型 | [s1-oss-models-receipt.json](../reports/s1-oss-models-receipt.json) | 39 | 27,023,759,360 |
| 教师输出、训练wheels等 | [s2-teacher-oss-receipt.json](../reports/s2-teacher-oss-receipt.json) | 6 | 3,471,360 |
| 中断恢复对照checkpoint | [s2-training-recovery-oss.json](../reports/s2-training-recovery-oss.json) | 17 | 444,743,680 |
| 128步checkpoint和合并Draft | [s2-trained-assets-oss.json](../reports/s2-trained-assets-oss.json) | 35 | 3,317,524,480 |
| 两组128量化、校准数据与AWQ依赖 | [s2-awq-g128-oss.json](../reports/s2-awq-g128-oss.json) | 30 | 11,164,968,960 |
| 领域64量化产物 | [s2-awq-g64-oss.json](../reports/s2-awq-g64-oss.json) | 16 | 5,709,936,640 |
| 固定GPU环境本体快照 | [s1-environment-receipt.json](../reports/s1-environment-receipt.json) | 1 | 4,130,582,075 |
| 36基础本地wheel及两份清单 | [s5-base-wheels-oss.json](../reports/s5-base-wheels-oss.json) | 38 | 1,330,974,720 |

以上为v1.0.0历史索引：182对象、53,125,961,275bytes，约0.510009元/天，原索引和收据保留不改。2026-10-16另按用户要求增加以下容器迁移资产：

| 新增内容 | 完整读回收据 | 对象数 | 归档字节 |
|---|---|---:|---:|
| 固定系统用户态、Python/venv/CUDA工具与源码容器镜像 | [container-image-oss.json](../reports/container-image-oss.json) | 1 | 10,232,606,095 |
| 独立源码/恢复材料包与校验索引包 | [container-recovery-kit-oss.json](../reports/container-recovery-kit-oss.json) | 2 | 27,373,533 |

当前项目总计185对象、63,385,940,903bytes；新增10,259,979,628bytes。按0.0004元/GB/小时估算合计约0.608505元/天，新增约0.098496元/天。实际以平台计费为准，不设置旧30GB上限。容器恢复步骤与平台Ubuntu版本限制见[固定容器恢复](container-recovery.md)；验证边界见[迁移报告](../reports/container-image-validation.json)。

所有对象有完整上传后归档/成员读回收据；当前182对象存在性和10小成员重新恢复见[S5核验](../reports/s5-assets.json)。小探针不代表再次全量下载了所有权重。OSS读取需要项目账户权限；Git仓库不含账户凭据或大模型权重。

| 数据用途 | 条数 | 场景组 | 固定文件 |
|---|---:|---:|---|
| train | 512 | 128 | [data/frozen-v1/train.jsonl](../data/frozen-v1/train.jsonl) |
| calibration | 256 | 64 | [data/frozen-v1/calibration.jsonl](../data/frozen-v1/calibration.jsonl) |
| dev | 128 | 32 | [data/frozen-v1/dev.jsonl](../data/frozen-v1/dev.jsonl) |
| test | 256 | 64 | [data/frozen-v1/test.jsonl](../data/frozen-v1/test.jsonl) |

split按场景组和精确内容隔离；仍共享规则与schema。教师640条仅来自train/dev，472条合格train用于128步序列蒸馏；AWQ通用/领域各16384tokens与final-test隔离。最终test256只用于冻结验收。数据来源、生成规则及使用边界见[数据说明](data.md)，校准来源与附加层见[AWQ协议](awq-protocol.md)。

Target为Qwen2.5-7B-Instruct，原Draft为1.5B-Instruct；精确revision/tokenizer文件锁见[models](../configs/models.json)。对齐Draft、训练Draft和各组自主量化模型具有各自provenance，不能将零填词表或下载上游AWQ算作训练/校准。

GPU基础153项锁、训练/AWQ附加层、上游SHA和三组补丁均在历史索引definitions中列hash。原锁重建路线中，36个file URL引用已有独立wheel备份，其他117个索引版本仍需要包索引；原venv快照不包括宿主Python/驱动/工具包，overlay绝对软链接需重建。新增容器镜像已包含系统Python、用户态库、CUDA工具和固定依赖，保留原路径；宿主驱动仍在镜像之外。恢复命令、空间要求及CLI路径映射见[复现说明](reproduce.md)。

没有实际宿主迁移或物理24GB验证；/hy-netdisk本实例是overlay，核心留存由GitHub与OSS承担。普通备份/校验按工作单元执行，没有后台定时同步或关机后自动工作。
