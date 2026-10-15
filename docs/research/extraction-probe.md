# qwen3.8-max LLM 知识建模实测记录

实测时间：实施 Task 15 Step 1。原始输出见 `scripts/probe_extraction.py` 运行记录（不含密钥）。

## 模型名可用性

- `qwen3.8-max` 经百炼兼容模式调用成功，百炼已发布 Qwen3.8-Max（2.4 万亿参数 MoE，2026-08 发布）。
- 结论：**默认模型名 `qwen3.8-max` 成立，无需回退**。

## 实体与关系抽取 schema 稳定性

- 连续调用 JSON 均合法，实体 3 条、关系 2 条，结果一致；时延 18~24 秒/次；约 1050~1280 tokens/次。

## 本体归纳 schema 稳定性

- 连续 3 次调用 JSON 均合法（classes=10、object_properties=8~10）；输出字段完整（local_name 为英文标识符、label/definition 为中文、domain/range 引用 classes 标签）。
- **时延 75~115 秒/次，约 3700~5200 tokens/次**——归纳比抽取慢约 5 倍；单次调用超时须放宽到 180 秒。
- 倾向过度归纳（3 句话归纳出 10 个类）：prompt 增加「最多输出 6 个类与 4 个对象属性，只保留最核心、出现频率最高的概念」。

## 官方单价

- 官方价格页（[模型调用计费](https://help.aliyun.com/zh/model-studio/model-pricing)）华北2（北京）：`qwen3.8-max` 输入 1.650、输出 4.951（每百万 tokens；国际站美元口径，国内账单口径以控制台为准）。
- 估算取值：**输入 0.00165 元/千 tokens**（按人民币口径近似）。
- 单切片抽取约 0.0017 元；单切片归纳约 0.006~0.009 元；采样 20 片归纳约 0.15 元。

## 由此确定的 .env 取值

- `KB_EXTRACT_MODEL=qwen3.8-max`（可用，无需回退）
- `KB_EXTRACT_PRICE_PER_1K_TOKENS=0.00165`
- `KB_EXTRACT_CONCURRENCY=2`
- `KB_INDUCT_SAMPLE_LIMIT=20`（归纳调用 75~115 秒/次，采样 20 片约 13~20 分钟）

## 备注

- 归纳 prompt 与抽取 prompt 长度远低于上下文上限，无截断风险。
- 限流：并发 2 的请求速率远低于官方限流阈值。
