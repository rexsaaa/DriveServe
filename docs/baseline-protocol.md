# S2 原生基线的有限调优协议

在 M2 四组 eager 机制实验之后冻结以下探索，模型、36条合成 token 输入、128块KV池、波次、seed、输出32及缓存重置规则不变。该协议在 B0/B1 实验开始前进入 Git，不能事后按收益改选择标准。

- B0：未经 DriveServe 补丁的固定原 wheel，APC、eager、max_seqs=4。此前已发现上游 WAITING 前缀计数陈旧，保留它作为原始运行/正确性对照；如果输出不一致则不能作为有效优化收益分母。
- B1候选：保留同一项 WAITING 前缀正确性修复的原生 LRU/FCFS，四个原生配置为 eager/sequences4、CUDA Graph/sequences2、Graph/sequences4、Graph/sequences8；只调原生参数，不启用个人冷热或长度规则。eager候选沿用已完成正式结果，其他各跑一次。未搜索更大配置或改显存预算。
- 选择：先要求请求全部成功、与已验证参考36条贪心 token一致，再按计量波次总时长最小选择。若存在输出差异，保留差异并检查，不把质量变化当加速。初次选择可能受噪声影响，S3需独立重复。
- 选定后：保持B1参数不变，再跑 cache/scheduler/both，四组主比较均不带观察器。Graph捕获与预热不计入请求时间，仍记录启动资源成本。观察器/eager四组承担机制验证，无须把它们冒充调优主比较。

`benchmark_policies.py --variant native --upstream` 是 B0；`--variant native --graph --max-seqs 2|4|8` 是三个新 B1 候选。报告中区分“纯原版B0”与“修正已证实缺陷后的原生策略B1”，该正确性修复的贡献不计入cache或scheduler收益。这里只是合成引擎诊断的B1，业务服务和部署比较还需各自冻结合适基线。
