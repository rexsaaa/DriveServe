# 存储边界与 S1 资产留存方案

2026-10-14 用户提供的平台截图说明：`/hy-netdisk` 在同一内网主机上的实例之间共享，仅带内网存储标识的部分机器支持。平台将其描述为高持久性存储，但该说明不承诺迁移到任意主机后仍可访问。

当前实例检查结果见 `reports/storage-inspection-20261014.json`：项目路径和 `/hy-netdisk` 都解析到 30GiB overlay，`/proc/1/mountinfo` 未发现独立内网存储挂载；`/hy-tmp` 是独立 50GiB XFS 临时盘。不能仅因目录名相同就认定本实例已经接入截图中的内网存储。尚未执行关机或迁移验证，也不需要为了验证而额外租机。

截图中的内网存储免费总量为 10GB，当前计费为 0 元/小时。页面上“已用 10.00GB”与下方免费空间“0/10.00GB”口径不明确，不据此推断剩余可用量。当前模型有效载荷为 27.023473848GB，即使完整 10GB 免费空间可用也不足以保存全部模型。

## 已完成的保留与读回

源码、配置、完整依赖版本锁、数据样例、小型原始运行记录和报告已推送至 GitHub。原 Target/Draft 在项目 artifacts 中有第二份副本；两份完整文件均重新计算 SHA256，见 `reports/s1-model-assets.json`。这是本地读回，不是跨实例备份。

| 资产 | 有效载荷（十进制 GB） | 当前位置 | 额外本地副本 |
|---|---:|---|---|
| Qwen2.5-7B-Instruct | 15.2428 | `/hy-tmp/driveserve/models/target` | `artifacts/models/target-weights` |
| Qwen2.5-1.5B-Instruct | 3.0990 | `/hy-tmp/driveserve/models/draft` | `artifacts/models/draft-weights` |
| 零填充派生 Draft | 3.0993 | `/hy-tmp/driveserve/models/draft-aligned-v1` | 无；可由已保存原模型与导出脚本重建 |
| 上游 AWQ 格式冒烟模型 | 5.5824 | `/hy-tmp/driveserve/models/awq-smoke` | 无；固定上游 revision 和文件 hash |

`scripts/inventory_models.py` 会读取全部模型文件，并检查原 Target/Draft 第二份本地副本；产物同时记录各文件大小、SHA256、派生关系与脚本 hash。GPU 环境本体位于临时盘；保存的锁和 bootstrap 脚本已在全新目录验证可重建。还没有训练 checkpoint 或自主量化产物。

## 可执行的备份选择

1. **新增最多 30GB OSS 存储**：覆盖上述四组资产、provenance 和打包索引，当前载荷约 27.03GB。按截图 0.0004 元/GB/小时估算，30GB 上限的新增存储费约 0.288 元/天、8.64 元/30 天；这是存储费估计，平台计费单位和其他费用需以平台为准。现有账户已用空间不删除、不计入这次新增上限。
2. **暂不新增费用**：继续当前实例上的实现准备，保留 GitHub 代码证据和本地权重；S1 持久资产条件保持未满足。等待接入已有且容量足够的持久路径，再读回验证。不会将仅 10GB 免费内网额度描述为足够保存全部模型。

平台已安装 `oss` v1.2.36+prod，但只读 `oss ls` 返回 401 Authentication Failed。若选择 OSS，需要用户在终端执行 `oss login` 完成平台身份验证，不能将账号密码、token 或私钥发到聊天或仓库。成功登录后先只读列目录确认目标，再上传独立的 DriveServe 目录；不修改既有云端文件。

上传方案为逐文件生成独立无压缩 tar（工具帮助限制上传归档格式），附带原始模型 provenance 和清单；逐包上传、下载读回并比较归档和内容 SHA256，生成远端 URI/大小/hash 的收据。按文件分包避免当前 16GiB 左右临时剩余空间需要同时容纳 27GB 总包。仅在收据确认后清理可再生成的临时归档，不删除模型、原始证据或用户资产。

**当前状态：用户已授权新增最多 30GB OSS，尚未上传，等待终端登录生效。** 授权已记录 AGENTS.md，不重复请求该范围内许可。`scripts/backup_models_oss.py` 实现按包上传/读回、30,000,000,000 字节硬上限、任务锁和原子收据；在确认 OSS 真实前缀后先 dry-run，固定代码再通过命令记录器运行 `--upload`。每包验证后清理脚本生成的临时归档，源模型始终保留。存储接入或备份读回完成后才更新 S1 验收状态。
