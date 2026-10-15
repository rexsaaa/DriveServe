# 快速开始

从仓库根目录执行，使用Python 3.11、Linux x86_64和支持`--python`的pip。完整CPU测试不需要GPU或模型；HTTP依赖采用实测版本，aiohttp安装包由项目OSS收据恢复。OSS需要已获授权的项目账户；在平台终端登录，凭据不写入仓库。

```bash
oss login
oss ls oss://DriveServe/s5-base-wheels-1f6207f4cc2e/
python3 scripts/restore_models_oss.py --receipt reports/s5-base-wheels-oss.json --destination artifacts/cpu-wheels --include assets/w/aiohttp-3.14.5-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl --report artifacts/cpu-wheel-restore.json
python3 scripts/bootstrap_cpu.py --env .venv-cpu --http-tests --wheelhouse artifacts/cpu-wheels
.venv-cpu/bin/driveserve demo --dataset data/frozen-v1/dev.jsonl
.venv-cpu/bin/driveserve doctor
```

恢复入口校验归档及成员SHA256；bootstrap校验原锁中的wheel hash后重写路径，拒绝覆盖已有环境。其余固定版本依赖仍从包索引下载；需要时添加`--index https://mirrors.cloud.tencent.com/pypi/simple`或已有代理的`--proxy http://127.0.0.1:7890`。不要把示例代理地址当作已经在新机器启动的服务。

`demo`明确标注rule-oracle，只展示数据/评分链路，不调用语言模型。不安装`--http-tests`时可以使用基础CLI，但HTTP测试会跳过，不能记作完整39项通过。完整新环境的实际验证状态见[S6验收](stages/S6/acceptance.md)。

保存结果的CPU复算（无模型推理）：

```bash
.venv-cpu/bin/python scripts/analyze_s5_final.py --state reports/s5-final-quality-state.json --protocol configs/s5-final-quality.json --report artifacts/quality-recomputed.json
.venv-cpu/bin/python scripts/analyze_s5_openloop.py --states reports/s5-timing-v2-r1-state.json reports/s5-timing-v2-r2-state.json reports/s5-timing-v2-r3-state.json --report artifacts/openloop-recomputed.json
```

正式GPU环境、模型与六线实验见[复现说明](reproduce.md)。先读[最终结论](s5-discussion.md)和[配置范围](s5-compatibility.md)，再选择与自己负载匹配的实验入口。
