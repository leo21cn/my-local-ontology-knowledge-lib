# 百炼 text-embedding-v4 嵌入实测记录

实测时间：实施 Task 3。原始输出见 `embedding-probe-raw.txt`（不含密钥）。

## 实测批上限

- batch=1 ok、batch=10 ok、batch=20/50/100 FAIL：`batch size is invalid, it should not be larger than 10`。
- 结论：**单批上限 10 条**。`KB_EMBED_BATCH=10`。

## 实测单条长度上限

- 500、1000、3000、8000 字符均 ok（约 1 字符 = 1 token）。
- 16000 字符 FAIL：`Range of input length should be [1, 16000]`；32000 字符反而返回 ok（上游口径不稳定）。
- 结论：**取 8000 字符为安全上限**。当前切片上限 700 字符远低于该值，不受影响。

## 支持的维度取值

- 实测 1024、1536、2048 均返回对应长度向量。
- 官方文档：支持 64~2048 维自定义。
- 本项目选定 **1024**（`KB_EMBED_DIM=1024`）。

## 官方单价

- 官方文档（[text-embedding-v4](https://help.aliyun.com/zh/model-studio/text-embedding-v4)）华北2（北京）：文本输入 **0.5 元/百万 tokens**，即 0.0005 元/千 tokens。
- 与 `.env` 默认 `KB_EMBED_PRICE_PER_1K_TOKENS=0.0005` 一致，**无需修改**。

## 实测与官方口径差异

| 项 | 官方标称 | 实测 |
| --- | --- | --- |
| 批上限 | 未标称 | 10（超过报错） |
| 单条长度上限 | 未标称（API 报错提示 [1,16000]） | 8000 字符安全，16000 报错、32000 偶发成功 |
| 维度 | 64~2048 自定义 | 1024/1536/2048 均可用 |
| 单价 | 0.5 元/百万 tokens | 一致（按官方价估算） |

## 由此确定的 .env 取值

- `KB_EMBED_BATCH=10`（实测批上限）
- `KB_EMBED_DIM=1024`（选定维度）
- `KB_EMBED_PRICE_PER_1K_TOKENS=0.0005`（官方单价）
- 切片默认值维持 700 字符上限 / 60 字符重叠，远低于单条安全上限，不需要调整。

## 限流口径（官方文档）

华北2（北京）：RPM 1800、TPM 1,200,000。全量重嵌入 200 篇语料（约 800 切片 → 80 批）远低于限流阈值。
