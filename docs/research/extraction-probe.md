# qwen3.8-max LLM 抽取实测记录

实测时间：实施 Task 15 Step 1。原始输出见 `scripts/probe_extraction.py` 运行记录（不含密钥）。

## 模型名可用性

- `qwen3.8-max` 经百炼兼容模式调用成功（3/3 次），百炼已发布 Qwen3.8-Max（2.4 万亿参数 MoE，2026-08 发布）。
- 结论：**默认模型名 `qwen3.8-max` 成立，无需回退**。

## 输出 JSON 稳定性

- 同一抽取 prompt 连续 3 次调用：JSON 均合法（`json_valid=True`），实体 3 条、关系 2 条，抽取结果一致。
- 抽取质量：`星河项目 → Project`、`张三/李四 → Person`、`张三/李四 belongsTo 星河项目` 全部正确。

## 单条时延与用量

- 时延：9.7~12.3 秒/次（约 10 秒），含 prompt（本体签名 + 文本）与输出。
- 用量：762~868 tokens/次（约 800 tokens，输入为主）。
- 推论：每切片一次调用；600 切片的库全量抽取约 100 分钟（并发 2）或 50 分钟（并发 4），费用估算见下。

## 官方单价

- 官方价格页（[模型调用计费](https://help.aliyun.com/zh/model-studio/model-pricing)）华北2（北京）：`qwen3.8-max` 输入 1.650、输出 4.951（每百万 tokens；国际站美元口径，国内账单口径以控制台为准）。
- 估算取值：**输入 0.00165 元/千 tokens**（按人民币口径近似）。
- 单切片调用约 800 tokens ≈ 0.0013 元；600 切片全库 ≈ 0.8 元。

## 由此确定的 .env 取值

- `KB_EXTRACT_MODEL=qwen3.8-max`（可用，无需回退）
- `KB_EXTRACT_PRICE_PER_1K_TOKENS=0.00165`
- `KB_EXTRACT_CONCURRENCY=2`

## 备注

- 抽取 prompt 长度（本体签名 + 切片正文）在 700 字符切片下远低于上下文上限，无截断风险。
- 限流：qwen3.8-max 并发 2 的请求速率远低于官方限流阈值。
