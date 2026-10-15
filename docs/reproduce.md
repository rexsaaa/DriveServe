# 最终复现说明

CPU重算保存结果、GPU重新测量、重新训练/校准是三类不同操作。首次使用从[快速开始](quickstart.md)进入；全部结果索引见[结果目录](results-index.md)，资产对象与校验值见[资产说明](assets.md)。S1–S5的历史入口保存在[历史说明](reproduce-through-s5.md)，当时的状态措辞只属于对应阶段。

## 固定环境与基础安装包

实际GPU环境为Python3.11、torch2.6.0+cu124、vLLM0.8.5、Transformers4.51.3；上游SHA为ba41cc90e8ef7f236347b2f1599eec2cbb9e1f0d。驱动、系统Python和CUDA toolkit属于宿主，需要另行核对；本次driver550.163.01、nvcc12.1，两RTX4090各49140MiB，无NVLink/P2P失败。未发生实际宿主迁移或物理24GB验证。

36个本地wheel与原GPU锁逐一匹配且完整备份。恢复到新目录，再按原hash重定位；另外117条固定版本依赖仍需要可用包索引，不能称完整离线wheelhouse。

```bash
python3 scripts/restore_models_oss.py --receipt reports/s5-base-wheels-oss.json --destination artifacts/base-wheels --report artifacts/base-wheels-restore.json
python3 scripts/relocate_lock.py --lock requirements/gpu.lock.txt --wheelhouse artifacts/base-wheels --output artifacts/gpu-relocated.lock.txt --report artifacts/gpu-lock-relocation.json
python3 scripts/bootstrap_gpu.py --env /hy-tmp/driveserve/gpu-new --uv /hy-tmp/driveserve/tools/bin/uv --cache /hy-tmp/driveserve/uv-cache-new --wheelhouse artifacts/base-wheels
```

`uv`固定为0.7.13（requirements/tools.txt），新实例需先安装该工具并调整路径。bootstrap在新目录创建环境，自动验证wheel并生成路径重写后的锁，执行pip check和gpu-smoke；原requirements/gpu.lock.txt保持不变。目录已经存在会拒绝覆盖。S1已在本实例按原锁完整独立重建过；S6新增路径入口的验证范围以其报告为准，不把仅重写锁或CPU安装称为再次完整GPU重建。

环境快照也完整保存在reports/s1-environment-receipt.json，但绝对shebang、宿主Python和editable路径有限制。迁移优先重建，不能仅复制旧venv或overlay目录。

## 模型、训练与校准资产

OSS按[八份收据](assets.md)恢复。省略`--include`会恢复整份收据，先检查本地容量；S1整份约27GB有效载荷，分包恢复还需最大归档/解包临时空间。可按收据精确成员名重复`--include`，只取需要的模型；小型config探针不等于恢复了权重。

```bash
python3 scripts/restore_models_oss.py --receipt reports/s1-oss-models-receipt.json --destination /hy-tmp/driveserve/restored-base --report artifacts/base-model-restore.json
python3 scripts/restore_models_oss.py --receipt reports/s2-trained-assets-oss.json --destination /hy-tmp/driveserve/restored-trained --report artifacts/trained-restore.json
python3 scripts/restore_models_oss.py --receipt reports/s2-awq-g128-oss.json --destination /hy-tmp/driveserve/restored-awq --report artifacts/awq-restore.json
```

对应目录分别为`restored-base/target`、`restored-base/draft_aligned`、`restored-trained/assets/distilled`及`restored-awq/assets/domain-g128`/`general-g128`。默认实验计划使用原机器的`/hy-tmp/driveserve/models/*`布局；新机器使用CLI的`--target`/`--draft`等参数或创建新的计划，不修改已冻结的历史计划后伪称同配置。

推理回放不需重训。重做序列蒸馏或AWQ时，先恢复teacher、checkpoint、冻结校准数据和附加层wheels，按[累计六线回放](stages/S5/replay.md)、[训练协议](distillation-protocol.md)、[量化协议](awq-protocol.md)操作。训练全状态恢复已实测；AWQ中断须整组重做。训练/AWQ是独立依赖层，不能覆盖基础推理环境。量化脚本的Target与training-layer部分路径固定，迁移须恢复原布局或明确改配置并复测，不承诺任意路径即用。

## 补丁、CUDA和六线实验

在锁定GPU环境中，从未修改的vLLM wheel重建三种overlay。脚本验证上游文件、补丁及输出hash，不修改原wheel；新目录不能已存在。

```bash
/hy-tmp/driveserve/gpu-new/bin/python scripts/build_vllm_overlay.py --destination /hy-tmp/driveserve/policies-new --patch-lock patches/vllm-v0.8.5-policies.json
/hy-tmp/driveserve/gpu-new/bin/python scripts/build_vllm_overlay.py --destination /hy-tmp/driveserve/spec-new --patch-lock patches/vllm-v0.8.5-spec.json
/hy-tmp/driveserve/gpu-new/bin/python scripts/build_vllm_overlay.py --destination /hy-tmp/driveserve/observers-new --patch-lock patches/vllm-v0.8.5-observers.json
```

M1插桩/Nsight、M2四策略/生命周期/heap、M3原/新Draft与固定/动态K、M4三组量化、M5独立CUDA与memcheck、M6 FA2/三部署的完整命令在[累计回放](stages/S5/replay.md)。迁移需要重新编译CUDA扩展并运行受影响的正确性/服务冒烟；新环境性能要重新测匹配baseline，不能直接复用旧卡百分比。

`configs/final-profiles.json`内`dev_replay_argv`给出十个已验证profile的开发集回放命令；路径仍为原实例，先适配新目录。默认FP16/native APC；AWQ×spec默认关闭，heap/自研策略/独立CUDA保留各自入口。未验证自研cache×spec×TP的统一进程。完整测试集已按冻结十profile各执行一次，日常复算使用保存输出；独立复现需新run，不能据test重选提示、模型或阈值。

## 原始结果复算与独立核查

```bash
python3 scripts/analyze_s5_composition.py --states reports/s5-timing-v2-r1-state.json reports/s5-timing-v2-r2-state.json reports/s5-timing-v2-r3-state.json --report artifacts/composition-recomputed.json
python3 scripts/analyze_s5_openloop.py --states reports/s5-timing-v2-r1-state.json reports/s5-timing-v2-r2-state.json reports/s5-timing-v2-r3-state.json --report artifacts/openloop-recomputed.json
python3 scripts/analyze_s5_final.py --state reports/s5-final-quality-state.json --protocol configs/s5-final-quality.json --report artifacts/quality-recomputed.json
python3 scripts/analyze_s5_final_gpu.py --state reports/s5-final-gpu-state.json --report artifacts/gpu-regression-recomputed.json
```

上述命令只读原始数据，无GPU执行。逐字节比较应在独立checkout中使用原reports相对输出路径；部分报告包含输出路径/文件hash，另选路径不能直接假设整份JSON字节相同。`verify_s5_release.py --checkout 独立GitHub目录 --output 验证目录 --python 完整CPU环境Python`会执行39项CPU、六份精确复算和证据审计。旧阶段使用对应tag与当时脚本，避免混用新聚合器。

## 任务恢复与资产管理

正式GPU实验先确认clean Git、真实进程与两卡空闲，一次只运行一项性能任务。`run_experiment_plan.py`保存PID/boot_id/start_ticks、30秒心跳与已完成单元；同源同plan可接续未执行单元，失败计时整单元重测，不拼接残缺性能。训练checkpoint另存optimizer/scheduler/RNG/cursor，按既有恢复协议续训。

`record_command.py`记录命令、子进程、日志和退出状态；`python3 -m driveserve status`核验真实任务。OSS脚本按工作单元上传/下载/校验，可由agent管理；当前没有后台定时同步、自动开机或agent自动唤醒。/hy-netdisk在本实例是overlay，不能作为已证实的跨主机持久目录。资产凭据不入Git，不删除唯一有效副本。
