# qwen 系列 LLM 知识建模实测记录

实测时间：实施 Task 15 Step 1 及后续控费调整。原始输出见 `scripts/probe_extraction.py`、`scripts/probe_thinking.py` 运行记录（不含密钥）。

## 模型切换结论（2026-10-17）

- 本体归纳与实体抽取已统一切换为 **`qwen3.8-flash`**（原 qwen3.8-max）。
- 实测（`probe_extraction.py`）：抽取 3 实体 + 1~2 关系、JSON 稳定、约 1.1K token/次、11~12 秒；归纳 4~6 类 + 4 属性、JSON 稳定、约 1.4~2K token/次、14~26 秒。质量与 max 相当。
- 单价（官方价格页，华北2北京）：输入 0.113 / 输出 0.382（每百万 token），比 qwen3.8-max（1.65/4.951）便宜约 **13~15 倍**。费用估算单价取输入价 0.000113 元/千 token。
- 调用统一 `enable_thinking: False`（见 probe_thinking.py：同任务 token 降 44%、耗时降 75%）。

## qwen3.8-max 实测（历史留档）

- 模型名可用、无需回退；抽取时延 18~24 秒、约 1050~1280 tokens/次；归纳时延 75~115 秒、约 3700~5200 tokens/次。
- 思考模式在复杂签名下每片膨胀至 2~2.5 万 token，且客户端超时后服务端仍计费——是 200 元账单主因，已通过关闭思考 + 换 flash 模型根治。

## 由此确定的 .env 取值

- `KB_EXTRACT_MODEL=qwen3.8-flash`
- `KB_EXTRACT_PRICE_PER_1K_TOKENS=0.000113`
- `KB_EXTRACT_CONCURRENCY=4`
- `KB_INDUCT_SAMPLE_LIMIT=10`

## 备注

- 归纳与抽取 prompt 均远低于上下文上限，无截断风险；并发 4 请求速率低于官方限流阈值。
