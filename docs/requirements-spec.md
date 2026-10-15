# 中心知识库需求规格说明书

版本：v1.0　　状态：需求规格　　依据：[docs/concept.md](concept.md)（v1.1）　　适用部署：单机 Docker Desktop

---

## 1. 引言

### 1.1 目的与范围

本说明书把概念文档中的功能需求 FR-01 至 FR-13、非功能需求 NFR-01 至 NFR-11 展开为实现可直接对照的规格：逐条给出触发条件、前置条件、输入、处理规则、输出、异常处理与关联验收判据，并定义接口契约、数据结构与配置项。实现与验收以本说明书为准，概念文档负责定位与边界。

本系统是个人知识资产的检索底座与语义索引层，三层职责边界与概念文档第 1 节一致，不在此重复。

### 1.2 文档链

概念需求（concept.md）→ 本说明书（requirements-spec.md）→ 实施步骤计划（implementation-plan.md）。实施计划中的每个任务引用本说明书的条目编号。

## 2. 总体描述

### 2.1 系统上下文

组件划分与数据流与概念文档第 5、6 节一致：api 与 worker 共用同一镜像两种角色，web 为管理界面，Qdrant、Neo4j、Redis 为本编排专属实例；外部依赖为百炼嵌入服务，消费方为 Dify 与 Qoder 等智能体。

### 2.2 运行环境与基线

- 部署：Docker Desktop（Windows），compose 项目名 `center-kb`，全部宿主端口绑定 127.0.0.1。
- 端口：web 8100、api 8101、Qdrant 6340 与 6341、Neo4j 7474 与 7687、Redis 6380。
- 后端：Python 3.12，FastAPI，pydantic v2，任务队列 arq（基于 Redis），neo4j 官方驱动，rdflib 负责 OWL 序列化，openai SDK 以兼容模式访问百炼。
- 前端：Vue 3 + Vite + Element Plus + vis-network，由 nginx 提供静态资源并反代 api。
- 镜像：统一走已配置加速前缀，锁定次版本标签，不使用 `latest`。

### 2.3 权威源约定

权威源根目录固定命名为 `knowledge-lib-base-folder`，默认位于项目目录下，以只读方式挂载进容器。目录内一切编辑视为对权威源的直接修改。库（Corpus）对应根目录下的一个子目录。文档为 Markdown 或纯文本，编码 UTF-8。

## 3. 详细功能需求

### FR-01 库管理

- 触发条件：界面发起创建、改名、归档、删除操作。
- 前置条件：创建时提供名称、权威源子目录、嵌入模型、向量维度、切片规则参数、本体命名空间前缀。
- 输入：字段见 5.4 节 Corpus 结构。
- 处理规则：创建时在 Qdrant 建立 collection（命名 `kb_<corpus_id>`，见 5.2 节），在 Neo4j 写入本体命名空间记录与 OntVersion 首版，导出空本体 TTL；嵌入模型与维度写入 collection 元数据，此后不可修改。改名仅改显示名。归档后库停止参与定时轮询与检索，数据保留。删除为级联操作：删除 collection、按库删除实例与本体数据、删除任务记录，不触碰权威源文件；删除前界面必须二次确认。
- 输出：库列表与详情，含文档数、切片数、点数、最近同步时间。
- 异常处理：权威源子目录不存在时拒绝创建并提示；collection 建立失败回滚本体写入。
- 关联验收：V1、V4。

### FR-02 同步触发

- 触发条件：手动按库、手动按单文件、定时轮询（默认 30 分钟，库级可配）。
- 处理规则：三种触发共用同一套增量判定（流程见 concept.md 第 6.1 节入库同步）。手动触发返回任务标识，界面轮询任务状态。定时轮询对每个启用库发起全库扫描，只对变更文档产生嵌入请求。删除权威源文件后触发同步：与已入库相对路径清单比对识别删除，对应切片与向量从索引移除，实体不自动删除，转待处理队列（kind=violation，reason=source_file_deleted）由人工裁决。一次同步内文档级并行准备、切片级批量嵌入。
- 输出：任务标识；任务记录含状态、处理文档数、变更文档数、嵌入请求条数、令牌数、费用估算、失败项清单。
- 异常处理：任务内单文档失败不中断整体，失败项按错误码分类处理（见 NFR-09 与 6.3 节嵌入后端契约）。
- 关联验收：V1、V2、V8。

### FR-03 切片查看

- 输入：库、文档相对路径。
- 输出：切片树（标题路径、序号、长度、内容哈希、嵌入状态），任一切片可查看正文。
- 处理规则：切片数据从 Qdrant 载荷读取，正文与权威源逐字一致由界面提供核对入口。
- 关联验收：V1、V3。

### FR-04 检索测试

- 输入：查询文本、库范围、返回条数（默认 10）、过滤条件（见 FR-05）。
- 输出：结果列表，每条含命中片段、所属小节完整上下文、锚点三元组、向量排名与融合后排名、分数、关联实体与关系路径。
- 处理规则：见 6.4 节检索编排。同一条结果可跳转到权威源文件对应行。
- 关联验收：V1、V7、V10。

### FR-05 元数据过滤检索

- 过滤条件三类：标签（文档 frontmatter 的 tags 字段）、时间范围（文档修改时间）、本体类型（类 IRI）。
- 处理规则：标签与时间范围在向量检索阶段以 Qdrant 过滤条件下推；本体类型过滤（filters 的 class_iri 字段）在向量召回后由图谱侧按子类闭包判定实例类型归属，排除不可达项。
- 关联验收：V1。

### FR-06 本体注册表

- 输入：类、对象属性、数据属性、公理的增删改查，字段见 5.3 节。
- 处理规则：见 6.2 节本体编辑与标准物化。保存时执行 OWL 2 RL 子集校验（见 NFR-01 附则），同时更新库内定义与 TTL 导出物，二者同事务；生成新 OntVersion 序号。
- 输出：保存结果、违规构造拒绝原因、受影响的实例违规清单（转待处理队列）。
- 关联验收：V5、V6。

### FR-07 实例校验

- 触发条件：本体保存后自动执行；也可按库手动重跑。
- 处理规则：对受影响的对象属性，检查所有以该属性建立的实例关系的两端类型是否满足 domain 与 range（含子类传递）；不相交类共实例检查。违规关系转待处理队列，可就地改类型或改关系类型后重验。
- 输出：违规清单（关系标识、两端实体、违规原因）。
- 关联验收：V6。

### FR-08 实体与关系建立

- 输入：手工新建实体（名称、类 IRI、别名）、手工新建关系（起终点实体、对象属性 IRI、证据锚点）、从提案确认或拒绝。
- 处理规则：实体标识由名称归一化后生成；写入时按本体定义校验，校验失败转待处理队列。确认后的关系状态为 confirmed，参与检索扩展；未确认的提案不参与。
- 关联验收：V7、V8。

### FR-09 实体归一

- 触发条件：界面检测到同名实体或别名冲突，或手工选择两个实体合并；手工选择实体并选定其锚点子集发起拆分。
- 处理规则：合并时被合并实体的全部锚点与关系并入留存实体，然后删除被合并实体，无锚点丢失。拆分时为选定的锚点子集新建实体：锚点子集必须非空且为源实体锚点的真子集（拆分后源实体至少保留一个锚点），新实体需名称，类 IRI 默认沿用源实体类；拆分后锚点总数不变、归属正确。新实体不自动继承源实体的关系，如需关联走 FR-08。操作前展示影响范围并要求确认。
- 输出：合并或拆分后的实体详情，锚点数量变化。
- 关联验收：V3、V8。

### FR-10 图谱只读浏览

- 输入：实体标识，展开深度（1 或 2）。
- 输出：以该实体为中心的图数据（节点含名称、类 IRI、锚点数；边含对象属性 IRI、状态），按类型着色。界面不提供画布建关系。
- 关联验收：V7。

### FR-11 任务与花费面板

- 输出：按库聚合的同步进度、失败重试计数、嵌入请求条数、令牌数与费用估算、待处理队列积压数。
- 处理规则：数据来源为任务记录（见 5.3 节 OpsTask），费用估算 = 令牌数 × 单价（单价来自嵌入实测记录，见 4.4 节环境变量）。
- 关联验收：V1、V2。

### FR-12 对外接口

- 三类调用方：界面 HTTP、Dify 外部知识库契约、MCP 工具。三者复用同一套检索编排，同一条查询在三处返回的正文、分数与锚点一致。契约见第 4 节。
- 关联验收：V10。

### FR-13 备份与恢复辅助

- 输入：备份命令或界面入口；界面提供索引重建两个入口。
- 处理规则：备份脚本先停止全部服务，再对 Qdrant、Neo4j、Redis 三个命名卷做一致性快照（详见实施计划备份任务），连同权威源目录的版本库状态一并归档。界面提供结构重建与全量重嵌入两个入口：结构重建仅按当前切片规则重新切片与写载荷，不调用嵌入服务；全量重嵌入删除 collection 后重新切片并嵌入，执行前必须返回预估切片数与嵌入请求条数并二次确认。嵌入模型或向量维度变更不修改既有库，走新建库路径：新库指向同一权威源子目录并同步，验证通过后归档旧库。恢复脚本按第 8 节 V4 判据验证。
- 关联验收：V4。

## 4. 接口契约

### 4.1 HTTP 接口（界面与一般调用方）

基路径 `/api/v1`，除 `/healthz` 与 `/retrieval` 外全部要求请求头 `Authorization: Bearer <KB_AUTH_TOKEN>`。返回结构统一为 `{"data": ...}`，错误为 `{"error": {"code": "...", "message": "..."}}`，状态码与错误码对应关系在实施计划中固定。

| 方法 | 路径 | 用途 | 关键字段 |
| --- | --- | --- | --- |
| POST | /corpora | 创建库 | 见 FR-01 输入 |
| GET | /corpora | 库列表 | 含统计摘要 |
| GET | /corpora/{id} | 库详情 | 含文档数、点数、最近同步时间 |
| PATCH | /corpora/{id} | 改名或改切片规则（嵌入模型与维度除外） | — |
| DELETE | /corpora/{id} | 删除库 | 级联，二次确认由界面承担 |
| POST | /corpora/{id}/sync | 触发同步 | `scope: all \| file`，`file_path?`，返回 `task_id` |
| GET | /corpora/{id}/rebuild/estimate | 重建预估 | 切片数、嵌入请求条数、费用估算 |
| POST | /corpora/{id}/rebuild | 触发重建 | `mode: structure \| reembed`，返回 `task_id` |
| GET | /tasks/{task_id} | 任务状态 | 见 5.3 节 OpsTask |
| GET | /corpora/{id}/assets | 文档列表 | 相对路径、哈希、修改时间、切片数 |
| GET | /corpora/{id}/assets/{rel_path}/chunks | 切片树 | 见 FR-03 输出 |
| POST | /search | 检索 | 见 FR-04 输入；filters 支持 tags、time_from、time_to、class_iri；图扩展开关与权重按库配置；响应含 `vector_rank` 与 `fused_rank` |
| GET/POST | /ontology/classes | 类列表 / 新建 | 见 5.3 节 |
| GET/PATCH/DELETE | /ontology/classes/{iri} | 类读写 / 删除 | 删除时其声明实例转待处理队列 |
| GET/POST | /ontology/object-properties | 对象属性列表 / 新建 | — |
| GET/PATCH/DELETE | /ontology/object-properties/{iri} | 对象属性读写 / 删除 | 删除时该属性的已确认关系转待处理队列 |
| GET/POST | /ontology/datatype-properties | 数据属性列表 / 新建 | — |
| GET/PATCH/DELETE | /ontology/datatype-properties/{iri} | 数据属性读写 / 删除 | — |
| GET | /ontology/export/{corpus_id} | 下载 TTL | `application/text` |
| GET/POST | /entities | 实体列表 / 新建 | 见 FR-08 |
| POST | /entities/merge | 合并实体 | `keep`, `drop` |
| POST | /entities/split | 拆分实体 | `eid`, `new_label`, `class_iri?`, `anchors[]` |
| POST | /relations | 新建关系 | 见 FR-08；写入前按 domain/range 校验，违规转待处理队列 |
| GET | /pending | 待处理队列 | 分页 |
| POST | /pending/{id}/resolve | 裁决 | `action: confirm \| reject \| retype` |
| GET | /graph?entity_id=&depth= | 图谱浏览 | 见 FR-10 |
| GET | /stats/corpus/{id} | 花费面板数据 | 见 FR-11 |
| GET | /healthz | 健康检查 | 无鉴权 |

### 4.2 Dify 外部知识库契约

- 路径：`POST /retrieval`，请求头 `Authorization: Bearer <KB_AUTH_TOKEN>`。
- 请求：`{"knowledge_id": "<corpus_id>", "query": "...", "retrieval_setting": {"top_k": 10, "score_threshold": 0.0}}`。
- 响应：`{"records": [{"content": "...", "score": 0.8, "title": "<文档标题>", "metadata": {"source": "<rel_path>", "chunk_id": "...", "anchor": {...}}}]}`。
- 处理规则：内部走 6.4 节检索编排，knowledge_id 即库标识。确切契约以对 Dify 1.17.1 的一次实测为准（见 concept.md 第 10 节第 2 项），实测后本小节以实测结果修订。

### 4.3 MCP 工具

以流式 HTTP 方式挂载在 api 进程的 `/mcp` 路径，与 4.1 节接口共用同一令牌校验分支：MCP 客户端必须在请求头携带 `Authorization: Bearer <KB_AUTH_TOKEN>`，缺失或错误返回 401。工具三项：

1. `kb_search`：参数 `query, corpus_id, top_k?`（top_k 默认 10），返回与 4.1 节检索一致的记录。
2. `kb_graph_query`：参数 `entity_id, depth?`（depth 默认 2），返回图谱数据。
3. `kb_ontology_export`：参数 `corpus_id`，返回 TTL 文本。

### 4.4 环境变量清单

| 变量 | 用途 | 来源 |
| --- | --- | --- |
| DASHSCOPE_API_KEY | 百炼嵌入调用密钥 | 执行时向用户索取并 export 到终端，不落盘 |
| KB_AUTH_TOKEN | 接口调用令牌 | 本地环境文件，不进版本库 |
| KB_EMBED_MODEL | 嵌入模型名，默认 text-embedding-v4 | 可覆盖 |
| KB_EMBED_DIM | 向量维度，默认 1024 | 可覆盖 |
| KB_EMBED_BATCH | 单批嵌入条数，默认 10，以实测上限为准 | 可覆盖 |
| KB_EMBED_PRICE_PER_1K_TOKENS | 费用估算单价，取自实测记录 | 可覆盖 |
| KB_CORPUS_ROOT | 容器内权威源挂载点，默认 /corpus | 固定 |
| KB_POLL_INTERVAL_MINUTES | 定时轮询间隔，默认 30 | 可覆盖 |
| KB_ONTOLOGY_EXPORT_DIR | TTL 导出目录，默认 /ontology | 固定 |
| QDRANT_URL / QDRANT_API_KEY | Qdrant 连接 | 编排注入 |
| NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD | Neo4j 连接 | 编排注入 |
| REDIS_URL | 任务队列连接 | 编排注入 |

## 5. 数据需求

### 5.1 权威源目录

- 根目录 `knowledge-lib-base-folder`，其下每个子目录可声明为一个库。
- 文件编码 UTF-8；Markdown frontmatter 中的 `tags` 字段作为过滤检索的标签来源。
- 系统对目录只读；唯一例外是本体 TTL 导出目录，默认位于项目目录下 `ontology/`，随项目版本库管理。

### 5.2 Qdrant

- 每库一个 collection，命名 `kb_<corpus_id>`；创建时以元数据记录 `embedding_model`、`vector_dim`，二者不可变。
- 点标识：`chunk_id = sha256("<rel_path>::<chunk_sha256>").hexdigest()`，前 32 位十六进制，写入为 upsert 语义。
- 载荷字段：`corpus_id`、`asset_rel_path`、`asset_sha256`、`asset_mtime`、`seq`、`heading_path`、`char_len`、`chunk_sha256`、`tags`（数组）、`text`（切片正文）。
- 文档级内容哈希随该文档全部切片载荷冗余存储，同步时按相对路径滚动拉取比对，用于跳过未变更文档。

### 5.3 Neo4j

标签与唯一约束：

| 标签 | 唯一约束 | 关键字段 |
| --- | --- | --- |
| :OntClass | iri | iri, prefix_local, label_zh, definition, parent_iris[], disjoint_with[] |
| :OntObjProp | iri | iri, prefix_local, domain_iri, range_iri, characteristics[] |
| :OntDataProp | iri | iri, prefix_local, domain_iri, xsd_range |
| :OntVersion | corpus_id+seq | corpus_id, seq, exported_at |
| :Entity | eid | eid, corpus_id, label, class_iri, aliases[], ont_version |
| :Anchor | (rel_path, seq, sha256) | rel_path, seq, sha256（锚点节点，经 `(:Entity)-[:ANCHOR_OF]->(:Anchor)` 关联） |
| :Relation | 无 | type_iri, evidence_anchors（JSON 字符串）, state(confirmed) |
| :PendingItem | pid | kind(proposal/violation/embed_failed), payload, attempts, last_error_code, status |
| :OpsTask | task_id | task_id, kind(sync/rebuild), corpus_id, status, doc_total, doc_changed, doc_removed, chunks, tokens, embed_retries, cost_estimate, proposals, error_code, started_at, finished_at |

关系：`(:Entity)-[:INSTANCE_OF]->(:OntClass)`，`(:Entity)-[:ANCHOR_OF]->(:Anchor)`，`(:Entity)-[:REL]->(:Entity)`（属性键为上述 Relation 字段）。锚点不存实体属性而建模为独立节点：Neo4j 属性不支持对象数组，且锚点可能被多个实体共享。实例写入按 OntClass 与 OntObjProp 的 domain 与 range 校验。任务记录以 `Ops` 前缀标签与知识数据隔离，所有知识类查询显式限定标签集，不出现 Ops 数据。

### 5.4 其他结构

- Corpus 结构：id（36 字符标识）、name、subdir、embedding_model、vector_dim、chunk_max_chars、chunk_overlap、ontology_prefix、graph_expand_enabled（bool，默认 true）、graph_weight（float，默认 1.0，图扩展路的 RRF 权重）、archived、created_at。
- TTL 导出物：`<KB_ONTOLOGY_EXPORT_DIR>/<corpus_id>.ttl`，由 rdflib 以 turtle 序列化，前缀、类、属性、公理全部使用完整 IRI。

## 6. 关键算法规格

### 6.1 切片

输入 Markdown 文本，输出切片序列。规则：按标题层级（# 至 ######）切分，标题路径完整保留；单片长度上限默认 700 个中文字符（按字符计数，Unicode 码点），相邻片重叠 60 个字符；超出上限的单一小节按段落继续切分，段落边界优先于硬截断；frontmatter 块单独解析不进入切片正文。

### 6.2 本体校验（OWL 2 RL 子集）

允许构造白名单：子类、等价类、对象属性与数据属性、domain、range、属性特征（传递、对称、函数性、反函数性）、不相交、基数约束（最小 0、最大 1）。白名单之外的构造（并、交、补、属性链、限定基数、规则）在界面与接口直接拒绝，拒绝响应携带原因码。校验按规则实现，不做隐含公理推导。

### 6.3 嵌入调用与错误分类

调用百炼兼容模式接口。错误信封按 `error.code` 分类：`AuthenticationError` 与 401 类为 AUTH，限流类为 RATE，入参类（含超长、非法维度）为 INPUT，欠费类为 BILLING，其余为 UPSTREAM。RATE 与 UPSTREAM 在 worker 内重试 3 次（间隔 2、4、8 秒），AUTH、INPUT、BILLING 立即失败；失败切片转待处理队列（kind=embed_failed），任务记录 error_code。

### 6.4 检索编排

1. 查询文本经嵌入服务向量化。
2. Qdrant 按库过滤条件近邻召回 top-k 候选。
3. 图谱侧：以候选切片锚点关联的已确认实体为起点，做一跳扩展，收集扩展切片标识集。
4. 融合排序默认倒数排名融合：`score = Σ 1/(60 + rank)`，向量召回序与图扩展命中序各自成 rank，权重与是否启用图扩展为库级配置，默认启用。
5. 按锚点回源读取切片所属小节完整上下文；读不到则该结果标记失效并记入任务日志。结果中的命中片段取自向量载荷中的切片正文，上下文取自权威源回读，两者分开返回。
6. 返回结构携带锚点三元组。

## 7. 非功能需求规格

| 编号 | 条目 | 目标与验证方法 |
| --- | --- | --- |
| NFR-01 | 一致性与幂等 | 点标识与切片哈希派生规则见 5.2 节；验证方法 V2 |
| NFR-02 | 成本可控 | 增量判定以哈希门槛跳过未变更文档；全量重嵌入前界面给出预估请求条数并二次确认；验证方法 V2、V4 |
| NFR-03 | 密钥边界 | 密钥与令牌只经环境变量注入；验证方法 V9（界面、导出物、全量日志中检索不到密钥串） |
| NFR-04 | 网络与代理 | 容器显式声明代理变量，对百炼走大陆直连、不继承宿主代理；验证方法 V9 末段（关闭代理后一次同步仍成功） |
| NFR-05 | 文件监听 | 不用 inotify，手动触发与定时轮询内容哈希；验证方法 V2 |
| NFR-06 | 访问边界 | 宿主端口全部绑定 127.0.0.1；接口以单一本机令牌校验，HTTP、Dify 契约与 MCP 走同一校验分支；验证方法 V9（局域网不可达、无令牌请求 401） |
| NFR-07 | 端口规划 | 见 2.2 节；compose 项目名 center-kb；验证：与既有栈同启无端口冲突 |
| NFR-08 | 存储 | 权威源只读挂载；索引数据命名卷；验证方法 V4 |
| NFR-09 | 可观测性 | 任务状态、失败原因、错误码、重试次数、队列积压持久记录并按库聚合；验证方法 FR-11 判据 |
| NFR-10 | 性能 | 千级文档：单文件同步不含嵌入等待小于 2 秒；检索端到端 P95 小于 1.5 秒；全量重嵌入 30 分钟内。验证方法：V1 执行时记录实测值 |
| NFR-11 | 镜像 | 加速前缀拉取、锁次版本标签；验证：compose 文件内无 latest |

## 8. 验收对照

| 验收判据 | 覆盖条目 |
| --- | --- |
| V1 入库主干 | FR-01、FR-02、FR-03、FR-04、FR-05、FR-11、NFR-10 |
| V2 幂等 | NFR-01、NFR-02、NFR-05 |
| V3 双索引一致 | FR-03、FR-08、FR-09 |
| V4 整库重建 | FR-01、FR-13、NFR-08 |
| V5 本体标准合规 | FR-06、6.2 节 |
| V6 实例校验 | FR-06、FR-07 |
| V7 图谱辅助检索 | FR-04、FR-08、FR-10 |
| V8 提案闭环 | FR-02、FR-08、FR-09 |
| V9 访问与密钥边界 | NFR-03、NFR-04、NFR-06 |
| V10 对外接口 | FR-04、FR-12 |

## 9. 待确认项与闭环方式

沿用 concept.md 第 10 节四项，实施计划中的闭环安排如下：

1. 百炼嵌入参数（批上限、单条长度、维度取值、单价）：实施计划嵌入实测任务闭环，产出实测记录文档。
2. Dify 外部知识库契约：实施计划适配任务先行实测再固化实现，本说明书 4.2 节以实测结果修订。
3. 权威源宿主位置：本说明书按"项目目录下的 knowledge-lib-base-folder"执行，改动只需调整编排中的挂载变量。
4. 模型辅助抽取时机：不在本说明书范围内，待 V8 判据跑通后依据别名词典覆盖率另行决策。
