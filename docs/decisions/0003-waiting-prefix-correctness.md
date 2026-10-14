# ADR 0003：WAITING 前缀计数刷新与公平基线

状态：采用；2026-10-15，S2。

固定vLLM0.8.5 / ba41cc90 的 ComputedBlocksTracker 为连续Prefill保留缓存token数，但其条件也覆盖WAITING。在受限128块KV池、请求RECOMPUTE后等待时，原缓存块可被其他请求淘汰，旧计数仍被用于新block table。新增真实复用断言在f46b334的GPU实验捕获了未computed块；原wheel两块池最小复现确认淘汰后仍报4tokens，见 scripts/check_waiting_prefix.py 与20261015T011119+0800-e8b715c270。

选择在隔离overlay中将旧计数缓存条件收紧为RUNNING中的连续Prefill；WAITING重新查resident hash。890bb0b回归返回0，并通过原失败GPU压力场景。引用计数、hash计算、原分配和释放逻辑保持上游实现。为保护连续chunked Prefill，未一概删去缓存；chunked完整路径仍未验收，不将此修改扩大宣称为通用补丁。

没有通过移除断言掩盖问题，也未为绕开缺陷关闭APC；整版升级会引入更多变量，因此先采用可重放的最小修复。原wheel和失败overlay保留。上游报告/PR没有发送，未取得对外消息授权。

比较约束：B0明确使用未改wheel；M2四组和调优B1共用修复，因此缓存/调度增量不会掺入修复贡献。后续原版B0的36条最终token恰与修复版相同，不能据此声称已证实文本损坏，也不能据此否定实际计数错误。报告同时保留这两项事实。

复查条件：更换vLLM版本、启用chunked/speculative/multi-step/swap或新backend时，重查tracker语义与补丁适用性；上游修复后应移除重复补丁并重建匹配对照。当前未改动site-packages。
