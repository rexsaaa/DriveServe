# ADR 0001：可验证的 S1 基础

日期：2026-10-14。决定是当前实施选择，兼容性未通过的部分保持候选状态。

1. 保留原始规范包，仓库根目录 `AGENTS.md` 和 `docs/` 作为执行入口。作者与 remote 使用用户确认的信息；main 的关键工作独立提交，不提前打验收 tag。
2. 核心记录、规则任务和客户端仅依赖 Python 3.11 标准库，CPU 环境与 GPU 环境分离。宿主缺少 ensurepip，重建采用 `venv --without-pip`，由宿主 pip 的 `--python` 向指定环境安装固定构建工具；不改变宿主 PyTorch。
3. vLLM 候选基线为 v0.8.5，SHA 与压缩包 hash 见 `configs/upstream.json`。选择原因是该版本保留可读的 V0 Draft worker、PrefixCachingBlockAllocator、FA2 和 AWQ 路径。未选更新版本是为了先控制六线兼容验证范围；这不是最新版性能结论。GPU 验证失败时重新评估并记录版本变更。
4. 使用固定上游 SHA + 仓库内版本化补丁方案。现阶段尚无 vLLM 修改。下载文件在 `artifacts/upstream`，源码在 `third_party`，都可从锁定引用重建；不能仅修改 site-packages。
5. 模型保持 Qwen2.5-7B-Instruct / Qwen2.5-1.5B-Instruct，未更换家族或规模。metadata revision、文件 hash 见 `configs/models.json`。tokenizer 与模板相同，但目标/草稿 vocab_size 不同，V0 `SpecDecodeWorker._vocab_size` 断言不满足。需要验证并实现概率维度适配；不能用截断目标分布掩盖问题，不能称已兼容。
6. GPU 按量计费、当前持续开机，无用户确认的总预算上限或截止日期。使用当前实例，不购买新资源；控制试验规模。发现 `/hy-tmp` 独立 50GiB 临时盘，可存可重建环境；模型和关键证据仍需确认云盘持久性。`/hy-netdisk` 在容器内显示 overlay，用户认为是长期云盘；尚不构成迁移验证。
7. 网络使用用户授权的现有 mihomo 配置，按命令显式设置代理，不改 Codex endpoint/auth、不修改系统网络策略。GitHub 凭据采用本仓库专用 deploy key，私钥不进入仓库，服务端 key 授权由用户完成。

复查条件：vLLM/模型真实加载结果、容量实测、平台存储说明、推测解码概率形状验证。任何负结果都保留，不通过修改措辞消除缺口。
