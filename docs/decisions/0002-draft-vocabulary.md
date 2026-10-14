# ADR 0002：保留原权重的 Draft 词表维度对齐

状态：限定范围内已验证；S1 准备工作，不代表蒸馏或自适应解码完成。

Qwen2.5-7B-Instruct 与 Qwen2.5-1.5B-Instruct 的 tokenizer.json、模板和特殊 token 一致，但模型 vocab_size 分别为 152064 和 151936。原始 Draft 实际启动在 vLLM V0 `spec_decode_worker.py` 的等词表断言失败，见 run `20261014T221247+0800-770dbdad58`。不能仅凭 tokenizer 一致声称兼容。

选择保留模型家族、原始文件和上游拒绝采样器，用 `scripts/align_draft_vocab.py` 派生新的 Draft。1.5B 使用 tied embeddings；脚本将 embedding 扩展 128 行零值并更新配置，逐张量验证 338 个原张量的已有值完全不变。Target 不变。导出见 `20261014T221547+0800-62311d08c7`，文件索引包含源 revision、大小和 SHA256。

直接删除上游断言不能解决概率张量维度差异。替换模型会改变项目范围。修改采样器增加转换路径的风险更大，当前没有必要。因此选用可逆、可追踪的派生产物；不覆盖上游原模型。

零行仍参与 softmax，Draft 提议分布可能变化；这不是训练，也不能视为对原 Draft 的概率完全等价变换。Target 的验证和拒绝采样继续使用上游逻辑。固定 K=3 的 32 条开发样例全部完成，解码文本与普通 Target 贪心解码 32/32 一致，详见 `reports/s1-fixed-k-smoke.json`。这个结果仅支持所测贪心路径，随机采样分布、EOS 边界、动态 batch 和自适应 K 仍待验证。

后续蒸馏必须将训练数据、配方、checkpoint 与此兼容导出分开记录；更换 Draft、tokenizer 或 vLLM 版本时重审。固定 K 与普通服务的 APC 配置不同，因此本次不计算性能提升。
