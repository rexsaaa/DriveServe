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

合计182对象、53,125,961,275bytes，按已知0.0004元/GB/小时估算约0.510009元/天。实际以平台计费为准，不设置旧30GB上限。

所有对象有完整上传后归档/成员读回收据；当前182对象存在性和10小成员重新恢复见[S5核验](../reports/s5-assets.json)。小探针不代表再次全量下载了所有权重。OSS读取需要项目账户权限；Git仓库不含账户凭据或大模型权重。

| 数据用途 | 条数 | 场景组 | 固定文件 |
|---|---:|---:|---|
| train | 512 | 128 | [data/frozen-v1/train.jsonl](../data/frozen-v1/train.jsonl) |
| calibration | 256 | 64 | [data/frozen-v1/calibration.jsonl](../data/frozen-v1/calibration.jsonl) |
| dev | 128 | 32 | [data/frozen-v1/dev.jsonl](../data/frozen-v1/dev.jsonl) |
| test | 256 | 64 | [data/frozen-v1/test.jsonl](../data/frozen-v1/test.jsonl) |

split按场景组和精确内容隔离；仍共享规则与schema。教师640条仅来自train/dev，472条合格train用于128步序列蒸馏；AWQ通用/领域各16384tokens与final-test隔离。最终test256只用于冻结验收。数据来源、生成规则及使用边界见[数据说明](data.md)，校准来源与附加层见[AWQ协议](awq-protocol.md)。

Target为Qwen2.5-7B-Instruct，原Draft为1.5B-Instruct；精确revision/tokenizer文件锁见[models](../configs/models.json)。对齐Draft、训练Draft和各组自主量化模型具有各自provenance，不能将零填词表或下载上游AWQ算作训练/校准。

GPU基础153项锁、训练/AWQ附加层、上游SHA和三组补丁均在索引definitions中列hash。36个file URL引用已有独立wheel备份；其他117个索引版本仍需要包索引。快照不包括宿主Python/驱动/工具包，overlay绝对软链接需重建。恢复命令、空间要求及CLI路径映射见[复现说明](reproduce.md)。

没有实际宿主迁移或物理24GB验证；/hy-netdisk本实例是overlay，核心留存由GitHub与OSS承担。普通备份/校验按工作单元执行，没有后台定时同步或关机后自动工作。
