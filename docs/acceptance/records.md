# 中心知识库验收记录（V1~V10）

执行日期：2026-10-15。执行环境：单机 Docker Desktop，compose 项目 center-kb。

## V1 入库主干 — 通过

- 语料：`knowledge-lib-base-folder/acceptance/` 200 篇 Markdown（含唯一表述 `ACCEPT-XXXX-UNIQUE`、两个标签、共享别名「验收项目组」出现在 note-003/047/121）。
- 建库：`c87917f13144`（验收库，subdir=acceptance，text-embedding-v4，dim=1024，切片 700/60）。
- 同步：全量同步 status=done，doc_total=200、doc_changed=200、chunks=601（note-007/010 在 V2/V7 中追加过内容）、tokens=13531、cost=0.006766 元、retries=0。
- 检索：查询 `ACCEPT-0042-UNIQUE`，首条 `note-042.md` seq=0，score=0.016393，vector_rank=1，context 与文件逐字一致（`context in file` 为 True）。

## V2 幂等 — 通过

- 无修改再同步：status=done，doc_changed=0、tokens=0、cost=0。
- 修改 note-007 后同步：doc_changed=1、tokens=73；点数修改前后均为 601，不增长。
- 嵌入请求条数：无变更时 0 次（worker 日志无 embeddings 调用）。

## V3 双索引一致 — 通过

- 任取检索结果（note-047.md seq=1，sha=c9bf37fb…）：向量载荷锚点 = Neo4j 实体锚点（实体 bc15606bfa7db95fc410ee03 的 Anchor 节点）三者互相可解析。
- 实体节点无正文字段（Entity 仅 eid/label/class_iri/aliases/ont_version）。
- context 与权威源文件逐字一致（`context in file` 为 True）。

## V4 整库重建 — 通过

- 备份：`backups/20261015-154847/`（qdrant/neo4j/redis 三卷 tar.gz + meta.json），先停全部服务再打包。
- 删卷：`docker compose down` + 删除三个命名卷后空库启动。
- 重建：仅凭权威源目录与本体重建库 `c87917f13144`，全量同步 done（200 文档、13531 tokens、0.006766 元），V1 判据复现。
- 结构重建入口：`POST /rebuild` mode=structure → done，chunks=601、tokens=0、cost=0（不产生嵌入请求）。
- 全量重嵌入入口：mode=reembed 全流程验证通过（删除 collection 后重建，见 V1 数据）；estimate 返回预估切片数与请求条数。

## V5 本体标准合规 — 通过（程序侧）

- 导出 TTL：`@prefix kb: <http://kb.local/o/acc#>` + owl/rdfs 前缀声明，类与属性以完整 IRI（前缀展开）序列化，含 rdfs:label、rdfs:comment，belongsTo 带 rdfs:domain（Person）与 rdfs:range（Project）。
- rdflib 以 turtle 格式重新解析无错误（11 triples）。
- OWL 2 RL 白名单校验：白名单外构造（相对 IRI、max_cardinality=3 等）被拒绝（测试覆盖）。
- Protégé 打开确认：留给用户人工执行（本记录更新后补充）。

## V6 实例校验 — 通过

- 建 Person 实体「人员甲」与 Project 实体「项目乙」，建立 belongsTo 关系（valid）。
- 将 belongsTo 的 range_iri 改为 Person 并保存：响应 violations=1、queued=1，原关系出现在 `GET /pending`（reason=range），无静默丢弃。
- 恢复 range 后逐条裁决：队列清零。

## V7 图谱辅助检索 — 通过

- 构造：实体「验收项目组」（锚定 note-047/121 关联节）与「人员丙」（锚定 note-010 补充节，该节含查询词但向量分低）通过已确认 belongsTo 关系相连。
- 图扩展开启（库配置 graph_expand_enabled=true）：查询「验收项目组」top_k=3，note-010 切片进入结果集（vector_rank 为空、fused_rank=2）。
- 关闭后：note-010 不进入。分数与排名差异在结果中可见。

## V8 提案闭环 — 通过

- 同步生成 3 条「验收项目组」提案（note-003/047/121 的关联节锚点）。
- 逐条 confirm：三条归并为同一 eid（bc15606bfa7db95fc410ee03），锚点数 1→2→3。
- 拆分验证（FR-09）：拆出 note-003 锚点后，原实体 2 锚点、新实体 1 锚点，锚点总数不变。

## V9 访问与密钥边界 — 通过

- 局域网地址（192.168.31.111）curl 宿主端口全部超时不可达。
- `docker logs kb-api kb-worker` 全文检索不到 DASHSCOPE_API_KEY。
- ontology/ 与 web/dist 中检索不到 KB_AUTH_TOKEN。
- 容器显式 NO_PROXY=*、HTTP(S)_PROXY 为空，百炼直连；全量同步在无代理容器内完成。

## V10 对外接口 — 通过

- 同一条查询 `ACCEPT-0042-UNIQUE` 三处调用：界面 HTTP、Dify 契约 `POST /retrieval`、MCP `kb_search`（流式 HTTP + Bearer 令牌）。
- 三者返回一致：首条 note-042.md、anchor sha 6096b4dd…、score 0.016393。
- `grep run_search app/kb`：实现仅一处（kb/search.py）。

## V11 LLM 抽取闭环 — 通过

- 语料：`note-v11.md` 含别名未覆盖表述「星河交付」（本体类「项目」别名仅有「项目组/验收项目组」，别名匹配对「星河交付」产不出提案，实测同步 proposals=0）与关系句「张三属于星河交付」。
- 手动触发：`POST /corpora/364db128e988/extract`（scope=file, file_path=note-v11.md），任务 kind=extract、status=done，extract_calls=2、extract_tokens=1644、proposals=7、extract_discarded=0、extract_failed=0、extract_cost_estimate=0.002713 元。
- 提案：pending 出现实体提案（星河交付→Project、张三/李四→Person）与关系提案（张三 belongsTo 星河交付），锚点均指向 note-v11 切片。
- 确认：confirm 关系提案后两端实体自动建立（Person 张三、Project 星河交付，各 1 锚点），关系建立（图谱 2 节点 1 边），domain/range 校验通过；检索「星河交付」首条命中 note-v11.md#1。
- 幻觉校验：本次模型无幻觉输出（discarded=0）；幻觉丢弃逻辑由单测 `test_parse_extraction_discards_hallucinated_term` 与 `test_parse_extraction_discards_unknown_iri` 覆盖。
- 成本：单切片调用约 800 tokens ≈ 0.0013 元（单价 qwen3.8-max 输入 0.00165 元/千 tokens，见 [docs/research/extraction-probe.md](research/extraction-probe.md)）。

## 待人工闭环

1. V5：用户以 Protégé 打开 `ontology/<corpus_id>.ttl` 确认无解析错误。
2. Dify 侧注册（Task 12 Step 8）：在 Dify「知识库 → 外部知识库 API」登记 `http://api:8101`（kb-shared 网络）或经用户确认后采用 `http://host.docker.internal:8101` 并在此记录偏离；API Key 填 .env 中 KB_AUTH_TOKEN，knowledge_id 填库标识。
3. 嵌入模型/维度变更流程（可选）：新建库指向同一子目录 → 同步 → 验证后归档旧库。

## 实施修正记录（与文档差异）

见 docs/implementation-plan.md 文末「实施修正记录」章节（锚点节点模型、{iri:path} 路由、变更资产先删旧点、任务 ID 统一、UUID 归一化、版本锁定、构建镜像源等）。
