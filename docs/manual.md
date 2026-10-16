# 中心知识库操作手册（manual）

> 适用对象：本机唯一使用者。
> 适用状态：系统已按 [implementation-plan.md](implementation-plan.md) 实施完成并通过 V1~V10 验收（记录见 [docs/acceptance/records.md](acceptance/records.md)）。
> 本文档从「当前状态」出发，说明如何把知识库日常管理起来。设计依据见 [concept.md](concept.md) 与 [requirements-spec.md](requirements-spec.md)。

---

## 1. 系统现状与总览

### 1.1 组件与端口（全部仅本机可访问）

| 组件 | 地址 | 用途 |
| --- | --- | --- |
| Web 管理界面 | http://127.0.0.1:8100 | 库管理、同步、检索测试、本体、实体、图谱、统计 |
| API | http://127.0.0.1:8101 | HTTP 接口、Dify 契约 `/retrieval`、MCP `/mcp/` |
| Qdrant | 127.0.0.1:6340（REST）/ 6341（gRPC） | 切片正文与向量 |
| Neo4j | 127.0.0.1:7474（浏览器）/ 7687（Bolt） | 本体、实体、关系、待处理队列、任务记录 |
| Redis | 127.0.0.1:6380 | arq 任务队列与定时轮询 |

compose 项目名固定为 `center-kb`，六个容器：`kb-qdrant`、`kb-neo4j`、`kb-redis`、`kb-api`、`kb-worker`、`kb-web`。

### 1.2 目录与凭据

```
D:\szp\work\my-center-knowledge-lib
├── knowledge-lib-base-folder\   ← 权威源根目录（唯一正文权威，随 Git 管理）
│   └── acceptance\              ← 当前验收库的语料（200 篇回归数据集，可保留）
├── ontology\                    ← 本体 TTL 导出物（<corpus_id>.ttl，随 Git 管理）
├── .env                         ← 密钥与配置（不进版本库，勿外泄）
├── .env.example                 ← 配置模板
├── docker-compose.yml
├── app\  web\  scripts\         ← 代码与工具脚本
├── backups\<时间戳>\            ← 备份产物
└── docs\                        ← 文档（本手册在 docs\manual.md）
```

- `.env` 内 `KB_AUTH_TOKEN`：访问 API 与 Web 界面的令牌（首次打开界面会弹窗输入）。
- `DASHSCOPE_API_KEY`：`.env` 中保持空值；执行容器操作时在**当前终端** export 注入（见 9.1 节），不写入任何文件。
- 当前验收库：`364db128e988`（名「验收库」，绑定 `acceptance` 子目录，模型 text-embedding-v4，维度 1024，切片 700 字符/60 重叠）。您自建的库（如 `ba-knowledge/finance`）与验收库互不影响。

### 1.3 核心概念（一句话版）

- **权威源**：`knowledge-lib-base-folder` 下的 Markdown 文件。一切编辑只发生在文件上；系统只读。
- **库（Corpus）**：权威源根目录下的一个子目录 + 一个 Qdrant collection + 一套本体命名空间。库是同步/统计/权限的最小单位。
- **同步**：把子目录内变更的 Markdown 切成切片、调百炼嵌入、写入 Qdrant，并按本体别名产出实体提案。
- **锚点**：`(文档相对路径, 切片序号, 内容哈希)` 三元组，是索引回指权威源的唯一凭据。
- **待处理队列**：实体提案、本体校验违规、嵌入失败的兜底出口，全部需要人工裁决。

---

## 2. 日常启停

```powershell
cd D:\szp\work\my-center-knowledge-lib
docker compose ps                 # 查看状态
docker compose up -d              # 启动全部（开机后一般已自动启动，restart=unless-stopped）
docker compose stop               # 停止全部（做备份时使用）
docker compose logs -f kb-worker  # 观察同步与定时轮询日志
```

容器配置了 `restart: unless-stopped`，Docker Desktop 启动后通常自动拉起。确认健康：

```powershell
curl.exe -s http://127.0.0.1:8101/healthz        # 期望 {"status":"ok"}
curl.exe -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8100/   # 期望 200
```

---

## 3. 把笔记变成可检索的知识

### 3.1 写入权威源

1. 在 `knowledge-lib-base-folder\` 下新建一个子目录（例如 `notes\`），作为你的库目录。
2. 用你习惯的编辑器（Obsidian、VS Code 等）直接在其中写 Markdown / 纯文本（UTF-8 编码，扩展名 `.md`/`.markdown`/`.txt`）。
3. 可选：在文件头写 frontmatter 标签，用于过滤检索：

```markdown
---
tags: [项目A, 会议纪要]
---

# 2026-10-15 项目A 周会

## 结论
...
```

> 说明：本体提案的别名词典在同步时按「类名与别名出现在切片正文」做子串匹配，因此给重要术语写全称（如「验收项目组」）更利于抽取。

### 3.2 新建库

打开 Web 界面 → 「库管理」→「新建库」，填写：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| 名称 | 显示名 | 个人笔记 |
| 权威源子目录 | 相对 `knowledge-lib-base-folder` 的子目录，必须已存在 | notes |
| 本体前缀 | 本体命名空间后缀（创建后不再变） | notes |
| 嵌入模型 / 向量维度 | 默认 text-embedding-v4 / 1024，**创建后不可修改** | 默认 |
| 切片上限 / 重叠 | 默认 700 / 60 | 默认 |
| 图谱扩展 / 图谱权重 | 检索时是否启用一跳扩展与权重，可随时改 | 开 / 1.0 |

也可以命令行创建：

```powershell
$TOKEN = ((Get-Content .env | Where-Object { $_ -match '^KB_AUTH_TOKEN=' }) -split '=',2)[1]
$h = @{ Authorization = "Bearer $TOKEN" }
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8101/api/v1/corpora" `
  -Headers $h -ContentType "application/json" `
  -Body '{"name":"个人笔记","subdir":"notes","ontology_prefix":"notes","vector_dim":1024}'
```

创建后系统自动：建 Qdrant collection、写本体命名空间、导出空 TTL 到 `ontology\<corpus_id>.ttl`。

### 3.3 触发同步

三种方式，共用同一套增量判定（以文件内容哈希为准）：

1. **手动全库**：界面「库详情」→「触发同步」；或 `POST /api/v1/corpora/{id}/sync` `{"scope":"all"}`。
2. **手动单文件**：`POST .../sync` `{"scope":"file","file_path":"子路径.md"}`（`file_path` 为库子目录内的相对路径）。
3. **定时轮询**：worker 默认每 30 分钟对未归档库做一次全库扫描，只对变更文档产生嵌入请求。间隔由 `KB_POLL_INTERVAL_MINUTES` 控制。

同步任务在「库详情」页实时显示进度：文档总数、变更数、移除数、切片数、令牌数、重试次数、费用估算、错误码。

**改文件 → 同步 → 检索** 是最短闭环。删除文件后触发同步，对应切片从索引移除；若已有实体锚定该文件，会产生一条待处理违规项（见第 8 节）。

### 3.4 费用说明

- 嵌入调用是唯一的按量支出。text-embedding-v4 官方价 0.5 元/百万 tokens（实测记录见 [docs/research/embedding-probe.md](research/embedding-probe.md)）。
- 全量重嵌入前界面会给出预估并二次确认；「统计」页可看累计令牌与费用估算。
- 批上限 10 条、单条安全上限 8000 字符（本项目切片 700 字符，远低于上限）。

---

## 4. 检索

### 4.1 界面检索测试

「检索测试」页：选库 → 输查询 → 选条数 → 可选标签过滤（逗号分隔）与类型过滤（类 IRI，留空不过滤）→「检索」。

结果字段：融合排名、向量排名、分数、命中片段、所属小节完整上下文（「展开」查看）、锚点、标题路径。命中片段取自索引，上下文取自权威源回读，**以回读结果为准**。

图谱扩展按库配置开关（「库管理」列表可见开关列；详情页可改 `graph_expand_enabled` 与 `graph_weight`）。

### 4.2 通过 API 检索（脚本 / 自动化）

```powershell
$TOKEN = ((Get-Content .env | Where-Object { $_ -match '^KB_AUTH_TOKEN=' }) -split '=',2)[1]
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8101/api/v1/search" `
  -Headers @{ Authorization = "Bearer $TOKEN" } -ContentType "application/json" `
  -Body '{"corpus_id":"c87917f13144","query":"你的问题","top_k":10,"filters":{"tags":["项目A"]}}'
```

过滤条件：`tags`（frontmatter 标签，Qdrant 阶段下推）、`time_from`/`time_to`（文件修改时间，Unix 秒）、`class_iri`（本体类型，按子类闭包由图谱侧判定）。响应每条含 `anchor` 三元组，调用方可自行校验正文是否变更。

### 4.3 Dify 外部知识库

- 端点：`POST /retrieval`，请求头 `Authorization: Bearer <KB_AUTH_TOKEN>`。
- 请求：`{"knowledge_id":"<corpus_id>","query":"...","retrieval_setting":{"top_k":10,"score_threshold":0.0}}`。
- 在 Dify 界面「知识库 → 外部知识库 API」登记：端点填 `http://api:8101`（需先按 4.4 打通网络），API Key 填 `KB_AUTH_TOKEN`，knowledge_id 填库标识。若不便改 Dify 容器网络，可降级为 `http://host.docker.internal:8101`（属对 NFR-06 的偏离，建议记录）。

### 4.4 打通 Dify 容器网络（一次性）

```powershell
docker network create kb-shared
docker network connect kb-shared <Dify 编排中 api 容器的名称或 ID>   # 例如 dify-api-1
```

在 `docker-compose.yml` 的 api 服务加一行 `networks: [default, kb-shared]`，文件末尾追加：

```yaml
networks:
  kb-shared:
    external: true
```

然后 `docker compose up -d api`。

### 4.5 MCP（Qoder 等智能体）

- 端点：`http://127.0.0.1:8101/mcp/`（**注意尾斜杠**），流式 HTTP，请求头必须携带 `Authorization: Bearer <KB_AUTH_TOKEN>`。
- 工具三项：`kb_search(query, corpus_id, top_k=10)`、`kb_graph_query(entity_id, depth=2)`、`kb_ontology_export(corpus_id)`。
- 在智能体的 MCP 配置中登记该 URL 与 Bearer 令牌即可。

---

## 5. 本体管理

「库管理 → 某库 → 本体」：

- **类 / 对象属性 / 数据属性**：新建、修改、删除。修改与删除同样会物化 TTL 并递增本体版本。
- **删除的后果**：删类 → 其声明实例转待处理队列；删对象属性 → 以该属性建立的已确认关系转待处理队列。界面删除前会提示受影响数量。
- **OWL 2 RL 白名单**：子类、等价类、对象/数据属性、domain、range、传递/对称/函数性/反函数性、不相交、基数 0 或 1。白名单外构造直接拒绝并给出原因。
- **别名**：类的「别名」是提案生成的词典（例如给类「项目」配别名「验收项目组」）。保存后，下次同步时包含别名的切片会产生实体提案。

**导出与 Protégé 检查**：本体页「导出 TTL」下载 `ontology\<corpus_id>.ttl`，可用 Protégé 直接打开校验标准合规。

**导入 TTL**：本体页「导入 TTL」上传 Turtle 文件（UTF-8，≤1MB）批量写入本体：**upsert 语义**——已存在的 IRI 更新字段、新 IRI 创建，不会产生重复要素；白名单外或缺失必填字段（标签/定义）的条目**跳过**并在结果中列出原因；导入后自动重导出 TTL。对象属性导入会照常做 domain/range 校验，违规实例转待处理队列。

**domain/range 校验**：保存对象属性时，系统检查现有已确认关系，违规关系写入待处理队列（界面显示违规数），不会静默丢弃。

---

## 6. 实体、关系与图谱

「实体」页：

- **手工新建实体**：名称 + 类 IRI + 锚点（相对路径、序号、哈希）。
- **新建关系**：起点 eid、终点 eid、对象属性 IRI。写入前自动做 domain/range 校验；违规则**不落库**、返回违规原因并转待处理队列。
- **合并**：勾选两行合并，被合并实体的锚点与关系并入留存实体，无锚点丢失。
- **拆分**：勾选一行拆分，选定锚点子集（必须非空且留至少一个锚点在源实体）+ 新名称（类默认沿用源实体类）；拆分后锚点总数不变。

「图谱」页：默认**全部视图**一次展示库内全部实体与已确认关系（超过 500 个实体时截断并提示）；「中心实体」模式选实体、切深度（1/2 跳）浏览子图。**逐级下钻**：任一模式下点击节点即展开其下一级关系并合入画布，可不断点击深入；滚轮缩放、按住空白平移；「重置」恢复初始画面。实体按类着色、边显示属性本地名。**画布不提供建关系**，关系一律走实体页。

实体的锚点来自：提案确认（自动带切片锚点）或手工新建。

---

## 7. 提案闭环（别名 → 实体）

1. 在本体中给类配置别名。
2. 触发同步：包含类名或别名的切片生成「实体提案」。
3. 「待处理队列」页（左侧导航）按 kind 分组查看：
   - `proposal` 实体提案 → **确认**（成为实体，参与检索扩展）/ **拒绝** / **改类型**；
   - `relation_proposal` 关系提案 → **确认**（按对象属性 domain/range 自动建立两端实体并建关系）/ **拒绝**；确认失败（属性缺失等）会提示原因并保持待处理；
   - `violation` 校验违规（本体变更、删类、删属性、删文件锚点失效）→ 逐条裁决；
   - `embed_failed` 嵌入失败、`extract_failed` 抽取失败 → 查看错误码后确认或拒绝，必要时修复后重新同步/重新抽取。
4. 同一实体的多条提案确认后自动归并（相同类+名称 → 同一 eid，锚点累加）。

未确认的提案不参与检索扩展。

## 7.5 LLM 辅助知识建模（两阶段，手动触发）

空本体或别名词典覆盖不到的内容，可以用 LLM 两阶段建模：

1. 打开目标库的「本体」页 →「LLM 辅助知识建模」卡片，选范围（全部文档 / 指定文档）。
2. **第一步「归纳本体」**：点击后采样最多 20 个切片（每片约 1~2 分钟）调用 `qwen3.8-max`，产出候选**类、对象属性与数据属性**（含 IRI 预览、中文标签、定义）进入待处理队列的「本体提案」页签。归纳会先建类提案、再建属性提案，并做**结构校验**：属性引用的类不在「已确认类/队列类提案/本批类提案」中时，该属性不进入队列（计入任务丢弃数）——不会再出现确认时找不到类的死结。逐条**确认**（系统自动拼完整 IRI、解析 domain/range 标签、写本体并导出 TTL）或拒绝；需要修改时点**编辑**（可改本地名、标签、定义、别名、domain/range；对象属性 domain/range 为已确认类标签下拉，数据属性 range 为 xsd 类型下拉），保存后再点确认。确认失败会提示缺失的类标签与可选标签清单。与已入册要素**同 IRI 且标签一致**的重复提案会自动跳过生成，确认时也会提示「重复内容，已自动关闭」；同 IRI 但内容不同的冲突会提示编辑本地名。
3. **第二步「执行抽取」**：本体非空后才可执行（接口会拒绝空本体抽取），按已确认本体逐切片抽取实体与关系提案，进入「实体提案」「关系提案」页签，确认后成为实体/关系。
4. 两步都是独立手动任务，不在同步/定时轮询中执行；结果不直接生效，全部经人工裁决。费用与调用数在任务详情与「统计」页可见；归纳每片约 0.006~0.009 元、抽取每片约 0.002 元（qwen3.8-max 实测）。

---

## 8. 索引维护

### 8.1 结构重建（不花钱）

库详情 → 索引重建 →「结构重建」。仅按当前切片规则重新切片与写载荷、复用既有向量，**不调用嵌入服务**（tokens=0）。适用于修复载荷问题；切片规则变更后不适用。

### 8.2 全量重嵌入（花钱，先预估）

库详情 →「全量重嵌入」→ 系统先返回预估（切片数、嵌入请求条数、费用估算）→ 二次确认后执行：删除 collection、按权威源全量重嵌入。执行前会再次提示预估。

### 8.3 嵌入模型或维度变更

嵌入模型与维度**不可修改**。更换走「新建库」路径：

1. 新建库指向同一权威源子目录，选择新模型/维度；
2. 同步并验证检索质量；
3. 验证通过后归档旧库（详情页可改 `archived`；归档库停止定时轮询与检索）。

### 8.4 备份与恢复

`scripts/backup.sh`（Git Bash 环境）或等价 PowerShell：

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = "backups/$stamp"; New-Item -ItemType Directory -Force $out | Out-Null
$qkey = ((Get-Content .env | Where-Object { $_ -match '^QDRANT_API_KEY=' }) -split '=',2)[1]
curl.exe -s -H "api-key: $qkey" http://127.0.0.1:6340/collections > "$out/meta.json"
docker compose stop
$win = (Get-Location).Path
foreach ($pair in @("center-kb_qdrant-data:qdrant","center-kb_neo4j-data:neo4j","center-kb_redis-data:redis")) {
  $vol = $pair.Split(':')[0]; $name = $pair.Split(':')[1]
  docker run --rm -v "${vol}:/data" -v "$win/${out}:/backup" docker.m.daocloud.io/alpine:3.20 tar czf "/backup/$name.tar.gz" -C /data .
}
docker compose start
```

恢复（`scripts/restore.sh <时间戳>`）或等价地：`docker compose down` → 清空并解包三个命名卷 → `docker compose up -d` → 按 V4 判据复验（检索命中、双索引一致）。

**权威源目录与本体 TTL 不在备份范围内**——它们由 Git 版本库单独保障，务必随笔记一起提交。

### 8.5 整库重建（兜底）

停止服务、删除三个命名卷、`docker compose up -d`，然后仅凭权威源 + `ontology\*.ttl` 重新建库、建本体、同步即可（验收 V4 已验证该路径）。

---

## 9. 安全与密钥

### 9.1 百炼密钥注入（易踩坑，务必照做）

`DASHSCOPE_API_KEY` **不写入 .env**。容器内调用百炼依赖该变量，规则：

- 在**同一终端会话**先 export，再执行 `docker compose up -d`（compose 优先读当前 shell 环境变量注入容器）：

```powershell
$env:DASHSCOPE_API_KEY = "sk-你的密钥"
docker compose up -d worker api
```

- 已启动容器的环境变量随容器保留，自动重启无需重复注入；但**新开终端**执行 compose 命令前必须重新 export，否则重建/启动的容器会拿到空密钥（症状：同步任务失败、错误码 AUTH）。
- 验证：`docker exec kb-worker env | Select-String DASHSCOPE` 应显示 `sk-...`。

### 9.2 令牌

- `KB_AUTH_TOKEN` 在 `.env` 中（不进版本库）。Web 界面首次访问弹窗输入后存于浏览器 localStorage；输错会提示重新输入。
- HTTP、Dify 契约、MCP 三者共用同一令牌校验分支，无令牌请求一律 401。

### 9.3 边界

所有宿主端口绑定 127.0.0.1，局域网不可达（V9 已验证）。容器对百炼直连（`NO_PROXY=*`、清空 HTTP(S)_PROXY），不继承宿主代理。

---

## 10. 常见问题排查

| 症状 | 原因与处理 |
| --- | --- |
| 同步任务 status=failed 或 embed_failed 提案 | 先看任务 `error_code` 与待处理队列 payload：AUTH=密钥问题（检查 9.1）；RATE=限流（worker 已自动重试 3 次，稍后再同步）；INPUT=入参（批大小>10 或超长，检查 `.env` 的 KB_EMBED_BATCH）；BILLING=欠费 |
| 检索返回空 | ① 库已归档（归档库不参与检索）；② 未同步过该库；③ 过滤条件（标签/类型 IRI）过严；④ 查询与语料语言不匹配。逐项排除 |
| 修改文件后同步，检索仍是旧内容 | 界面检索展示「命中片段」取自索引、「上下文」取自权威源回读——若二者不一致说明未同步或同步失败，重新触发同步 |
| 界面 401 | 令牌错误或 localStorage 中的旧令牌失效，界面会清空并要求重新输入（取 `.env` 的 KB_AUTH_TOKEN） |
| 删除文件后实体仍在 | 符合设计：切片/向量已移除，实体不自动删除，相关锚点以 violation 进入待处理队列，由你裁决 |
| MCP 连接失败 | 使用 `http://127.0.0.1:8101/mcp/`（带尾斜杠）且请求头带 Bearer 令牌 |
| 界面出现 Bad Gateway (502) | web 容器内 nginx 对 api 的解析过期（api 容器重建后 IP 变化）。nginx 已配置为每请求动态解析（resolver 127.0.0.11），正常不会复发；如更换了 web 镜像或改动 nginx 配置后仍出现，执行 `docker compose up -d --build --force-recreate web` |
| 容器里无密钥（同步 AUTH 失败） | 见 9.1：新终端未 export 就执行了 compose 命令 |
| 中文在脚本里乱码 | 本机 PowerShell 命令行中文会被 GBK 破坏：脚本化调用请把 JSON 载荷写成 UTF-8 文件再读取注入；日常中文操作直接用 Web 界面（无此问题） |
| 定时轮询没生效 | worker 未启动或重启过；`docker logs kb-worker` 应见 `cron:poll_all` 计划行 |
| 端口冲突 | 本编排端口（8100/8101/6340/6341/7474/7687/6380）与既有栈错开；如改端口需同步改 compose 与 `.env` |

---

## 11. 附录

### 11.1 接口速查（基路径 /api/v1，全部需 Bearer）

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST/GET | /corpora、/corpora/{id} | 建库 / 列表 / 详情（PATCH 改配置，DELETE 级联删） |
| POST | /corpora/{id}/sync | 触发同步 `{scope: all\|file, file_path?}` |
| GET/POST | /corpora/{id}/rebuild/estimate、/corpora/{id}/rebuild | 重建预估 / 触发重建 `{mode: structure\|reembed}` |
| GET | /tasks/{task_id} | 任务状态 |
| GET | /corpora/{id}/assets、/assets/{rel_path}/chunks | 文档列表 / 切片树 |
| POST | /search | 检索（filters: tags/time_from/time_to/class_iri） |
| GET/POST/PATCH/DELETE | /ontology/classes[/{iri}] 等 | 本体注册表增删改查、导出 /ontology/export/{id} |
| GET/POST | /entities、/entities/merge、/entities/split | 实体管理 |
| POST | /relations | 建关系（写入前 domain/range 校验） |
| GET | /pending、/pending/{pid}/resolve | 待处理队列与裁决 |
| GET | /graph?mode=all&corpus_id= 或 /graph?entity_id=&depth= | 图谱浏览（全部视图 / 中心实体） |
| GET | /stats/corpus/{id} | 任务/令牌/重试/费用/失败/积压 |
| POST | /retrieval | Dify 外部知识库契约 |
| MCP | /mcp/ | kb_search / kb_graph_query / kb_ontology_export |

错误信封统一 `{"error":{"code","message"}}`。

### 11.2 环境变量（.env）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| KB_AUTH_TOKEN | — | 接口令牌（必填，随机生成） |
| DASHSCOPE_API_KEY | 空 | 终端 export 注入，不落盘 |
| KB_EMBED_MODEL / KB_EMBED_DIM | text-embedding-v4 / 1024 | 嵌入模型与维度（建库时固定） |
| KB_EMBED_BATCH | 10 | 单批嵌入条数（实测上限 10） |
| KB_EMBED_PRICE_PER_1K_TOKENS | 0.0005 | 费用估算单价（官方价） |
| KB_POLL_INTERVAL_MINUTES | 30 | 定时轮询间隔 |
| KB_EXTRACT_MODEL | qwen3.8-max | LLM 知识建模模型（手动触发才计费） |
| KB_EXTRACT_PRICE_PER_1K_TOKENS | 0.00165 | LLM 费用估算单价（实测） |
| KB_EXTRACT_CONCURRENCY | 2 | LLM 调用并发上限 |
| KB_INDUCT_SAMPLE_LIMIT | 20 | 本体归纳的切片采样上限 |
| QDRANT_API_KEY / NEO4J_PASSWORD / REDIS_PASSWORD | — | 组件密码（随机生成，勿外泄） |

### 11.3 验收语料说明

`knowledge-lib-base-folder\acceptance\` 是 V1~V10 验收的 200 篇回归语料（含唯一检索标识 `ACCEPT-XXXX-UNIQUE`），当前库 `c87917f13144` 即绑定该目录。可作为回归数据集长期保留；如需清空：删除该子目录并触发一次同步，索引随之清理（实体相关锚点转待处理队列裁决）。

### 11.4 文档链

[concept.md](concept.md)（概念与边界）→ [requirements-spec.md](requirements-spec.md)（需求规格与契约）→ [implementation-plan.md](implementation-plan.md)（实施步骤与修正记录）→ [docs/acceptance/records.md](acceptance/records.md)（验收记录）→ 本手册（日常操作）。
