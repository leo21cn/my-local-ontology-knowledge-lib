# 中心知识库本机实施步骤计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在单机 Docker Desktop 上建成「knowledge-lib-base-folder 权威源 + Qdrant 检索索引 + Neo4j 语义索引」的个人中心知识库，含 Web 管理界面与对外接口。

**Architecture:** 后端为单镜像双角色（api 与 worker 共用一个 Python 包），arq 承担任务队列与定时轮询；权威源目录只读挂载，Qdrant、Neo4j、Redis 均为本编排专属实例；本体按 OWL 2 RL 子集校验并物化为 TTL 文件。

**Tech Stack:** Python 3.12、FastAPI、pydantic v2、arq、qdrant-client、neo4j 驱动、rdflib、openai SDK（百炼兼容模式）；Vue 3 + Vite + Element Plus + vis-network；nginx；Qdrant、Neo4j Community、Redis。

**Spec:** [docs/concept.md](concept.md)（v1.1）与 [docs/requirements-spec.md](requirements-spec.md)（v1.0）。每个任务标注其落实的 FR/NFR 编号。

## Global Constraints

- 端口（全部绑定 127.0.0.1）：web 8100、api 8101、Qdrant 6340 与 6341、Neo4j 7474 与 7687、Redis 6380。
- compose 项目名固定 `center-kb`，不使用默认项目名；镜像走加速前缀 `docker.m.daocloud.io`，锁定次版本标签，禁用 `latest`。
- 权威源根目录 `knowledge-lib-base-folder` 只读挂载为容器内 `/corpus`；本体 TTL 导出目录 `ontology/` 挂载为容器内 `/ontology`。
- 切片规则默认值：单片上限 700 字符、相邻重叠 60 字符、标题层级优先、超长小节按段落续切；库级可配。
- collection 命名 `kb_<corpus_id>`；点标识 `chunk_id = sha256("<rel_path>::<chunk_sha256>")[:32]`；嵌入模型与维度写入 Corpus 记录且不可变。
- 本体建模限定 OWL 2 RL 子集白名单：子类、等价类、对象属性、数据属性、domain、range、传递、对称、函数性、反函数性、不相交、基数 0 或 1。不部署推理机。
- 嵌入错误分类固定为 AUTH、RATE、INPUT、BILLING、UPSTREAM；RATE 与 UPSTREAM 重试 3 次（间隔 2、4、8 秒），其余立即失败并转待处理队列。
- 密钥与令牌只经环境变量注入：`DASHSCOPE_API_KEY` 每次执行前向用户索取并 export 到当前终端，不写入任何文件。容器内调用百炼依赖该变量：启动或重建容器（`docker compose up -d`）前必须在同一 shell 会话中完成 export（compose 优先读取 shell 环境变量注入容器）；已启动容器的环境变量随容器保留，`restart: unless-stopped` 自动重启后无需重复注入，但新开终端执行 compose 命令前需重新 export。`KB_AUTH_TOKEN` 写入 `.env`，`.env` 不进版本库。
- 命令执行环境：bash 代码块默认在 Git Bash 中执行（工作区对应 `/d/szp/work/my-center-knowledge-lib`）；Windows 原生命令（`ipconfig`、browser-use MCP 调用等）在 PowerShell 或各自工具中执行，文中另有说明的除外。
- 错误信封：应用业务错误统一为 `{"error": {"code": "...", "message": "..."}}`；请求校验错误（422）保留 FastAPI 默认结构。
- MCP 端点与 HTTP、Dify 契约共用同一令牌校验分支（NFR-06），MCP 客户端须在请求头携带 `Authorization: Bearer <KB_AUTH_TOKEN>`。
- api 与 worker 容器显式清空 `HTTP_PROXY` 与 `HTTPS_PROXY` 并设 `NO_PROXY="*"`，确保对百炼直连、不继承宿主代理。
- 提交粒度：每个任务末尾至少一次 conventional commit（`feat:`、`fix:`、`chore:` 前缀）。
- 验收判据 V1 至 V10 见 requirements-spec.md 第 8 节；执行记录落 `docs/acceptance/records.md`。
- 代码不写注释；文档不写过程痕迹。

---

### Task 0: 项目初始化

落实：全部任务的目录与版本库前提。

**Files:**
- Create: `.gitignore`
- Create: `knowledge-lib-base-folder/.gitkeep`
- Create: `ontology/.gitkeep`
- Create: `docs/acceptance/.gitkeep`
- Create: `docs/research/.gitkeep`

**Interfaces:**
- Consumes: 无。
- Produces: 版本库根目录 `D:\szp\work\my-center-knowledge-lib`，以及 `app/`、`web/`、`scripts/` 三个后续任务要落代码的父目录。

- [ ] **Step 1: 建目录**

```bash
cd /d/szp/work/my-center-knowledge-lib
mkdir -p knowledge-lib-base-folder ontology docs/acceptance docs/research app/kb/routers app/kb/adapters app/tests web/src/pages web/src/components scripts
touch knowledge-lib-base-folder/.gitkeep ontology/.gitkeep docs/acceptance/.gitkeep docs/research/.gitkeep
```

- [ ] **Step 2: 写 .gitignore**

```gitignore
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
backups/
web/node_modules/
web/dist/
ontology/*.ttl.tmp
```

`.ttl` 文件本体不忽略，本体导出物随版本库管理。

- [ ] **Step 3: 初始化版本库并提交**

```bash
git init
git add .gitignore docs knowledge-lib-base-folder/.gitkeep ontology/.gitkeep
git commit -m "chore: init center knowledge lib skeleton"
```

若用户不希望在此目录建版本库，本步跳过，后续每个任务的 commit 步骤一并跳过，其余步骤不受影响。

---

### Task 1: 基础设施编排（Qdrant、Neo4j、Redis 专属实例）

落实：NFR-07、NFR-08、NFR-11、FR-01 的 collection 前提。

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Modify: `.gitignore`（已由 Task 0 建）

**Interfaces:**
- Consumes: 无。
- Produces: 三个专属容器与三个命名卷（`center-kb_qdrant-data`、`center-kb_neo4j-data`、`center-kb_redis-data`），后续任务全部以此为准连接：容器内 `http://qdrant:6333`、`bolt://neo4j:7687`、`redis://:<密码>@redis:6379/0`；宿主测试入口 `127.0.0.1:6340`、`127.0.0.1:7687`、`127.0.0.1:6380`。

- [ ] **Step 1: 写 docker-compose.yml（仅三个数据组件）**

```yaml
name: center-kb

services:
  qdrant:
    image: docker.m.daocloud.io/qdrant/qdrant:v1.18
    container_name: kb-qdrant
    ports:
      - "127.0.0.1:6340:6333"
      - "127.0.0.1:6341:6334"
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
    volumes:
      - qdrant-data:/qdrant/storage
    restart: unless-stopped

  neo4j:
    image: docker.m.daocloud.io/neo4j:5.26-community
    container_name: kb-neo4j
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
    volumes:
      - neo4j-data:/data
    restart: unless-stopped

  redis:
    image: docker.m.daocloud.io/redis:7-alpine
    container_name: kb-redis
    command: redis-server --requirepass ${REDIS_PASSWORD} --appendonly yes
    ports:
      - "127.0.0.1:6380:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  qdrant-data:
  neo4j-data:
  redis-data:
```

- [ ] **Step 2: 写 .env.example**

```dotenv
QDRANT_API_KEY=
NEO4J_PASSWORD=
REDIS_PASSWORD=
DASHSCOPE_API_KEY=
KB_AUTH_TOKEN=
KB_EMBED_MODEL=text-embedding-v4
KB_EMBED_DIM=1024
KB_EMBED_BATCH=10
KB_EMBED_PRICE_PER_1K_TOKENS=0.0005
KB_POLL_INTERVAL_MINUTES=30
KB_CORPUS_ROOT=/corpus
KB_ONTOLOGY_EXPORT_DIR=/ontology
```

- [ ] **Step 3: 生成 .env 并填入随机密钥**

```bash
cp .env.example .env
for k in QDRANT_API_KEY NEO4J_PASSWORD REDIS_PASSWORD KB_AUTH_TOKEN; do
  v=$(openssl rand -hex 16)
  sed -i "s/^$k=/$k=$v/" .env
done
cat .env
```

`DASHSCOPE_API_KEY` 保持空值，由 Task 3 与 Task 14 在执行时向用户索取并 export，不写入此文件。

- [ ] **Step 4: 校验编排语法与镜像标签可达**

```bash
docker compose config >/dev/null && echo "compose ok"
for img in docker.m.daocloud.io/qdrant/qdrant:v1.18 docker.m.daocloud.io/neo4j:5.26-community docker.m.daocloud.io/redis:7-alpine; do
  docker pull "$img" >/dev/null 2>&1 && echo "ok $img" || echo "MISSING $img"
done
```

Expected: 三行 ok。任一 MISSING 时，改用加速前缀下当前可拉取的次版本标签（`docker pull docker.m.daocloud.io/neo4j:5-community` 等回退一次），并把实际采用的标签回写到 compose 文件与本节，禁止改用 `latest`。

- [ ] **Step 5: 启动并记录解析到的镜像摘要**

```bash
docker compose up -d
sleep 20
docker compose ps --format "{{.Name}} {{.Status}}"
docker inspect kb-qdrant kb-neo4j kb-redis --format "{{.Name}} {{.Config.Image}}" > docs/research/image-pins.md
docker inspect kb-qdrant kb-neo4j kb-redis --format "{{.Name}} {{index .RepoDigests 0}}" >> docs/research/image-pins.md 2>/dev/null || true
```

Expected: 三个容器 Up。

- [ ] **Step 6: 健康检查与端口避让核对**

```bash
curl -s http://127.0.0.1:6340/healthz
curl -s http://127.0.0.1:7474/ | head -c 200
docker exec kb-redis redis-cli -a "$(grep '^REDIS_PASSWORD=' .env | cut -d= -f2)" ping
docker ps --format "{{.Ports}}" | grep -E "6333|6379|:80->" || echo "no port conflict"
```

Expected: `healthz check passed`；Neo4j 返回含 `neo4j_version` 的 JSON；`PONG`；最后一行输出既有栈端口占用情况，与本编排端口无重叠。

- [ ] **Step 7: 提交**

```bash
git add docker-compose.yml .env.example docs/research/image-pins.md
git commit -m "feat: add dedicated qdrant neo4j redis stack for center-kb"
```

---

### Task 2: 后端骨架（配置、鉴权、镜像、编排接线）

落实：NFR-03、NFR-04、NFR-06，以及 FR-01 至 FR-13 共用的接口骨架。

**Files:**
- Create: `app/pyproject.toml`
- Create: `app/Dockerfile`
- Create: `app/kb/__init__.py`、`app/kb/routers/__init__.py`、`app/kb/adapters/__init__.py`（空文件）
- Create: `app/kb/config.py`
- Create: `app/kb/auth.py`
- Create: `app/kb/main.py`
- Create: `app/tests/conftest.py`
- Create: `app/tests/test_health.py`
- Create: `app/tests/test_auth.py`
- Modify: `docker-compose.yml`（追加 api 与 worker 两个 service）

**Interfaces:**
- Consumes: Task 1 的三个容器与命名卷。
- Produces:
  - `kb.config.Settings`（pydantic-settings 字段见下）与 `kb.config.get_settings() -> Settings`（lru_cache）。
  - `kb.auth.require_token(request: Request) -> None`（async，401 时 detail 为 `{"code": "AUTH_REQUIRED", "message": "..."}`）。
  - `kb.main.create_app() -> FastAPI`，含无鉴权 `/healthz`，返回 `{"status": "ok"}`。

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "center-kb"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "httpx>=0.27",
  "openai>=1.40",
  "qdrant-client>=1.11",
  "neo4j>=5.24",
  "rdflib>=7.0",
  "python-frontmatter>=1.1",
  "arq>=0.26",
  "mcp>=1.2",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.21"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["kb", "kb.routers", "kb.adapters"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["integration: 需要本机容器与真实密钥"]
```

- [ ] **Step 2: 写 config.py**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kb_auth_token: str = "dev-token"
    dashscope_api_key: str = ""
    kb_embed_model: str = "text-embedding-v4"
    kb_embed_dim: int = 1024
    kb_embed_batch: int = 10
    kb_embed_price_per_1k_tokens: float = 0.0005
    kb_poll_interval_minutes: int = 30
    kb_corpus_root: str = "/corpus"
    kb_ontology_export_dir: str = "/ontology"
    qdrant_url: str = "http://127.0.0.1:6340"
    qdrant_api_key: str = ""
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    redis_url: str = "redis://127.0.0.1:6380/0"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

字段名与环境变量名大小写不敏感对应，不设前缀，因此 compose 中注入 `QDRANT_URL`、`NEO4J_URI`、`REDIS_URL` 即可。

- [ ] **Step 3: 写 auth.py**

```python
from fastapi import HTTPException, Request

from kb.config import get_settings


async def require_token(request: Request) -> None:
    expected = f"Bearer {get_settings().kb_auth_token}"
    if request.headers.get("authorization", "") != expected:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "缺少或无效的访问令牌"},
        )
```

- [ ] **Step 4: 写 main.py**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="center-kb", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: 写测试**

`app/tests/conftest.py`：

```python
import os

os.environ.setdefault("KB_AUTH_TOKEN", "test-token")

import pytest
from fastapi.testclient import TestClient

from kb.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def auth_headers() -> dict:
    return {"Authorization": "Bearer test-token"}
```

`app/tests/test_health.py`：

```python
def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

`app/tests/test_auth.py`：

```python
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from kb.auth import require_token
from kb.main import create_app


def _app_with_protected_ping() -> FastAPI:
    app = create_app()
    router = APIRouter(dependencies=[Depends(require_token)])

    @router.get("/api/v1/ping")
    async def ping() -> dict:
        return {"ok": True}

    app.include_router(router)
    return app


def test_protected_route_rejects_without_token():
    assert TestClient(_app_with_protected_ping()).get("/api/v1/ping").status_code == 401


def test_protected_route_accepts_with_token():
    resp = TestClient(_app_with_protected_ping()).get(
        "/api/v1/ping", headers={"Authorization": "Bearer test-token"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
```

- [ ] **Step 6: 装依赖并运行测试**

```bash
cd app
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]" -q
.venv/Scripts/python -m pytest -q
```

Expected: 3 passed。

- [ ] **Step 7: 写 Dockerfile**

```dockerfile
FROM docker.m.daocloud.io/python:3.12-slim
WORKDIR /srv
COPY pyproject.toml ./
COPY kb ./kb
RUN pip install --no-cache-dir .
EXPOSE 8101
CMD ["uvicorn", "kb.main:app", "--host", "0.0.0.0", "--port", "8101"]
```

- [ ] **Step 8: 在 docker-compose.yml 追加 api 与 worker**

```yaml
  api:
    build: ./app
    container_name: kb-api
    ports:
      - "127.0.0.1:8101:8101"
    volumes:
      - ./knowledge-lib-base-folder:/corpus:ro
      - ./ontology:/ontology
    environment:
      QDRANT_URL: http://qdrant:6333
      QDRANT_API_KEY: ${QDRANT_API_KEY}
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY}
      KB_AUTH_TOKEN: ${KB_AUTH_TOKEN}
      KB_EMBED_MODEL: ${KB_EMBED_MODEL}
      KB_EMBED_DIM: ${KB_EMBED_DIM}
      KB_EMBED_BATCH: ${KB_EMBED_BATCH}
      KB_EMBED_PRICE_PER_1K_TOKENS: ${KB_EMBED_PRICE_PER_1K_TOKENS}
      KB_POLL_INTERVAL_MINUTES: ${KB_POLL_INTERVAL_MINUTES}
      KB_CORPUS_ROOT: /corpus
      KB_ONTOLOGY_EXPORT_DIR: /ontology
      HTTP_PROXY: ""
      HTTPS_PROXY: ""
      NO_PROXY: "*"
    depends_on: [qdrant, neo4j, redis]
    restart: unless-stopped

  worker:
    build: ./app
    container_name: kb-worker
    command: arq kb.worker.WorkerSettings
    volumes:
      - ./knowledge-lib-base-folder:/corpus:ro
      - ./ontology:/ontology
    environment:
      QDRANT_URL: http://qdrant:6333
      QDRANT_API_KEY: ${QDRANT_API_KEY}
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: ${NEO4J_PASSWORD}
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY}
      KB_AUTH_TOKEN: ${KB_AUTH_TOKEN}
      KB_EMBED_MODEL: ${KB_EMBED_MODEL}
      KB_EMBED_DIM: ${KB_EMBED_DIM}
      KB_EMBED_BATCH: ${KB_EMBED_BATCH}
      KB_EMBED_PRICE_PER_1K_TOKENS: ${KB_EMBED_PRICE_PER_1K_TOKENS}
      KB_POLL_INTERVAL_MINUTES: ${KB_POLL_INTERVAL_MINUTES}
      KB_CORPUS_ROOT: /corpus
      KB_ONTOLOGY_EXPORT_DIR: /ontology
      HTTP_PROXY: ""
      HTTPS_PROXY: ""
      NO_PROXY: "*"
    depends_on: [qdrant, neo4j, redis]
    restart: unless-stopped
```

worker 的启动命令引用的 `kb.worker.WorkerSettings` 在 Task 8 才存在，因此本步只构建镜像、暂不启动 worker。

- [ ] **Step 9: 构建并启动 api，验证容器内健康检查**

```bash
docker compose build api worker
docker compose up -d api
sleep 5
curl -s http://127.0.0.1:8101/healthz
docker exec kb-api env | grep -E "PROXY|QDRANT_URL" 
```

Expected: `{"status":"ok"}`；`NO_PROXY=*`，`HTTP_PROXY` 与 `HTTPS_PROXY` 为空。

- [ ] **Step 10: 提交**

```bash
git add app docker-compose.yml
git commit -m "feat: add fastapi skeleton with token auth and dual-role compose services"
```

---

### Task 3: 百炼嵌入实测与嵌入后端

落实：NFR-02、NFR-03、NFR-04，requirements-spec.md 第 6.3 节；闭环 concept.md 第 10 节待确认第 1 项。

**Files:**
- Create: `scripts/probe_embedding.py`
- Create: `docs/research/embedding-probe.md`（实测记录）
- Create: `app/kb/embed.py`
- Create: `app/tests/test_embed.py`

**Interfaces:**
- Consumes: `kb.config.Settings`。
- Produces:
  - `kb.embed.EmbedErrorCode`（AUTH、RATE、INPUT、BILLING、UPSTREAM）。
  - `kb.embed.EmbedError(code: EmbedErrorCode, message: str)`。
  - `async kb.embed.embed_texts(settings: Settings, texts: list[str]) -> tuple[list[list[float]], int]`（向量列表与令牌总数）。
  - `kb.embed.classify_error(exc: Exception) -> EmbedErrorCode`。
  - `async kb.embed.embed_with_retry(settings, texts) -> tuple[list[list[float]], int, int]`（向量列表、令牌总数、实际重试次数；RATE 与 UPSTREAM 重试 3 次，间隔 2、4、8 秒）。

- [ ] **Step 1: 向用户索取百炼密钥并写入当前终端会话**

```bash
read -rs -p "DashScope API Key: " KEY && export DASHSCOPE_API_KEY="$KEY" && echo "key loaded"
```

密钥只存在于当前终端进程环境，不写入 `.env`、脚本或任何记录文件。

- [ ] **Step 2: 写实测脚本 scripts/probe_embedding.py**

```python
import os

from openai import OpenAI

BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = os.environ.get("KB_EMBED_MODEL", "text-embedding-v4")
client = OpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=BASE)


def probe_batch() -> None:
    for n in (1, 10, 20, 50, 100):
        try:
            resp = client.embeddings.create(model=MODEL, input=["测试文本"] * n, dimensions=1024)
            print(f"batch={n}: ok tokens={resp.usage.total_tokens}")
        except Exception as exc:
            print(f"batch={n}: FAIL {type(exc).__name__} {str(exc)[:160]}")


def probe_length() -> None:
    for chars in (500, 1000, 3000, 8000, 16000, 32000):
        try:
            resp = client.embeddings.create(model=MODEL, input="测" * chars, dimensions=1024)
            print(f"chars={chars}: ok tokens={resp.usage.total_tokens}")
        except Exception as exc:
            print(f"chars={chars}: FAIL {type(exc).__name__} {str(exc)[:160]}")


def probe_dims() -> None:
    for dim in (1024, 1536, 2048):
        try:
            resp = client.embeddings.create(model=MODEL, input=["测试"], dimensions=dim)
            print(f"dim={dim}: ok vector_len={len(resp.data[0].embedding)}")
        except Exception as exc:
            print(f"dim={dim}: FAIL {type(exc).__name__} {str(exc)[:160]}")


if __name__ == "__main__":
    probe_batch()
    probe_length()
    probe_dims()
```

- [ ] **Step 3: 执行实测**

```bash
python scripts/probe_embedding.py 2>&1 | tee docs/research/embedding-probe-raw.txt
```

Expected: 至少 `batch=1: ok`；出现 FAIL 的第一个值即上限的前一档。

- [ ] **Step 4: 取官方单价并写实测记录**

用 WebFetch 读取 `help.aliyun.com` 上百炼文本向量模型文档，取 `text-embedding-v4` 的单价与官方标称的批上限、单条长度上限，与实测结果交叉核对后写入 `docs/research/embedding-probe.md`，固定章节为：实测批上限、实测单条长度上限、支持的维度取值、官方单价（元/千令牌）、实测与官方口径差异、由此确定的 `.env` 取值。

- [ ] **Step 5: 按实测结果修订 .env 默认值**

把 `KB_EMBED_BATCH` 改为实测批上限、`KB_EMBED_DIM` 改为选定维度、`KB_EMBED_PRICE_PER_1K_TOKENS` 改为官方单价，同步修订 `.env.example` 的默认值与 requirements-spec.md 第 4.4 节变量表中的默认值说明。

- [ ] **Step 6: 写失败测试 app/tests/test_embed.py**

```python
import httpx
import pytest
import respx
from openai import APIError

from kb.config import Settings
from kb.embed import EmbedErrorCode, classify_error, embed_texts


@pytest.fixture
def settings() -> Settings:
    return Settings(kb_auth_token="t", dashscope_api_key="k", kb_embed_dim=1024)


@respx.mock
async def test_embed_texts_returns_vectors_and_tokens(settings):
    respx.post("https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1, 0.2], "index": 0}, {"embedding": [0.3, 0.4], "index": 1}],
                "usage": {"total_tokens": 8},
            },
        )
    )
    vectors, tokens = await embed_texts(settings, ["甲", "乙"])
    assert len(vectors) == 2
    assert vectors[1] == [0.3, 0.4]
    assert tokens == 8


@respx.mock
async def test_embed_texts_empty_input_skips_call(settings):
    route = respx.post("https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings")
    vectors, tokens = await embed_texts(settings, [])
    assert (vectors, tokens) == ([], 0)
    assert not route.called


def test_classify_error_arrearage_is_billing():
    exc = APIError("Arrearage: account is in arrears", request=None, body=None)
    assert classify_error(exc) == EmbedErrorCode.BILLING


def test_classify_error_unknown_is_upstream():
    assert classify_error(RuntimeError("socket closed")) == EmbedErrorCode.UPSTREAM
```

- [ ] **Step 7: 运行测试确认失败**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_embed.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'kb.embed'`。

- [ ] **Step 8: 写 app/kb/embed.py**

```python
import asyncio
from enum import Enum

from openai import APIError, AsyncOpenAI, AuthenticationError, BadRequestError, RateLimitError

from kb.config import Settings

BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
RETRY_DELAY_SECONDS = (2, 4, 8)


class EmbedErrorCode(str, Enum):
    AUTH = "AUTH"
    RATE = "RATE"
    INPUT = "INPUT"
    BILLING = "BILLING"
    UPSTREAM = "UPSTREAM"


class EmbedError(Exception):
    def __init__(self, code: EmbedErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def classify_error(exc: Exception) -> EmbedErrorCode:
    if isinstance(exc, AuthenticationError):
        return EmbedErrorCode.AUTH
    if isinstance(exc, RateLimitError):
        return EmbedErrorCode.RATE
    if isinstance(exc, BadRequestError):
        return EmbedErrorCode.INPUT
    text = str(exc)
    for marker, code in (
        ("Arrearage", EmbedErrorCode.BILLING),
        ("InvalidApiKey", EmbedErrorCode.AUTH),
        ("Throttling", EmbedErrorCode.RATE),
        ("InvalidParameter", EmbedErrorCode.INPUT),
    ):
        if marker in text:
            return code
    return EmbedErrorCode.UPSTREAM


async def embed_texts(settings: Settings, texts: list[str]) -> tuple[list[list[float]], int]:
    if not texts:
        return [], 0
    client = AsyncOpenAI(api_key=settings.dashscope_api_key, base_url=BASE_URL, timeout=60.0)
    try:
        resp = await client.embeddings.create(
            model=settings.kb_embed_model,
            input=texts,
            dimensions=settings.kb_embed_dim,
        )
    except Exception as exc:
        raise EmbedError(classify_error(exc), str(exc)) from exc
    finally:
        await client.close()
    return [item.embedding for item in resp.data], resp.usage.total_tokens


async def embed_with_retry(settings: Settings, texts: list[str]) -> tuple[list[list[float]], int, int]:
    retries = 0
    for delay in RETRY_DELAY_SECONDS + (None,):
        try:
            vectors, tokens = await embed_texts(settings, texts)
            return vectors, tokens, retries
        except EmbedError as exc:
            retryable = exc.code in (EmbedErrorCode.RATE, EmbedErrorCode.UPSTREAM)
            if not retryable or delay is None:
                raise
            retries += 1
            await asyncio.sleep(delay)
    raise EmbedError(EmbedErrorCode.UPSTREAM, "重试次数耗尽")
```

若已安装的 openai SDK 版本异常构造签名与 Step 6 的测试不符，以实际签名为准调整测试的构造方式，`classify_error` 的映射规则不变。

- [ ] **Step 9: 运行测试确认通过**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_embed.py -q
```

Expected: 4 passed。

- [ ] **Step 10: 用真实密钥跑一次端到端单条嵌入**

```bash
cd app && DASHSCOPE_API_KEY="$DASHSCOPE_API_KEY" .venv/Scripts/python -c "
import asyncio
from kb.config import Settings
from kb.embed import embed_texts
s = Settings()
v, t = asyncio.run(embed_texts(s, ['中心知识库连通性测试']))
print('dim=', len(v[0]), 'tokens=', t)
"
```

Expected: 输出维度等于 `KB_EMBED_DIM`，令牌数大于 0。此步验证 NFR-04 的直连策略（本终端不设代理）。

- [ ] **Step 11: 提交**

```bash
git add scripts/probe_embedding.py docs/research app/kb/embed.py app/tests/test_embed.py .env.example
git commit -m "feat: add dashscope embedding client with error classification and probe record"
```

---

### Task 4: Markdown 切片器

落实：FR-02、FR-03，requirements-spec.md 第 6.1 节。

**Files:**
- Create: `app/kb/chunker.py`
- Create: `app/tests/test_chunker.py`

**Interfaces:**
- Consumes: 无。
- Produces:
  - `kb.chunker.ChunkDraft`（dataclass，字段 `heading_path: list[str]`、`text: str`）。
  - `kb.chunker.extract_frontmatter(text: str) -> tuple[dict, str]`。
  - `kb.chunker.chunk_markdown(body: str, max_chars: int = 700, overlap: int = 60) -> list[ChunkDraft]`。
  - `kb.chunker.chunk_sha256(text: str) -> str`。

- [ ] **Step 1: 写失败测试 app/tests/test_chunker.py**

```python
from kb.chunker import chunk_markdown, chunk_sha256, extract_frontmatter


def test_headings_split_with_path():
    body = "# A\n甲甲\n\n## B\n乙乙\n\n# C\n丙丙"
    drafts = chunk_markdown(body, max_chars=700)
    assert [(d.heading_path, d.text) for d in drafts] == [
        (["A"], "甲甲"),
        (["A", "B"], "乙乙"),
        (["C"], "丙丙"),
    ]


def test_long_section_splits_with_overlap():
    body = "一" * 1500
    drafts = chunk_markdown(body, max_chars=700, overlap=60)
    assert len(drafts) == 3
    assert drafts[1].text.startswith(drafts[0].text[-60:])


def test_empty_heading_section_skipped():
    body = "# A\n\n## B\n正文"
    drafts = chunk_markdown(body, max_chars=700)
    assert [d.text for d in drafts] == ["正文"]


def test_frontmatter_tags_extracted():
    text = "---\ntags: [甲, 乙]\n---\n# T\n正文"
    meta, body = extract_frontmatter(text)
    assert meta["tags"] == ["甲", "乙"]
    assert body.startswith("# T")


def test_chunk_sha_stable():
    assert chunk_sha256("同一段文本") == chunk_sha256("同一段文本")
    assert chunk_sha256("同一段文本") != chunk_sha256("另一段文本")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_chunker.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'kb.chunker'`。

- [ ] **Step 3: 写 app/kb/chunker.py**

```python
import hashlib
import re
from dataclasses import dataclass

import frontmatter

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class ChunkDraft:
    heading_path: list[str]
    text: str


def chunk_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_frontmatter(text: str) -> tuple[dict, str]:
    try:
        post = frontmatter.loads(text)
    except Exception:
        return {}, text
    return dict(post.metadata), post.content


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 2 <= max_chars:
            buffer = f"{buffer}\n\n{paragraph}".strip()
            continue
        if buffer:
            parts.append(buffer)
        while len(paragraph) > max_chars:
            parts.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars - overlap:]
        buffer = paragraph
    if buffer:
        parts.append(buffer)
    return parts


def chunk_markdown(body: str, max_chars: int = 700, overlap: int = 60) -> list[ChunkDraft]:
    matches = list(HEADING_RE.finditer(body))
    if not matches:
        return [
            ChunkDraft(heading_path=[], text=part)
            for part in _split_long(body.strip(), max_chars, overlap)
            if part.strip()
        ]
    drafts: list[ChunkDraft] = []
    stack: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        content = body[match.end():end].strip()
        if not content:
            continue
        for part in _split_long(content, max_chars, overlap):
            if part.strip():
                drafts.append(ChunkDraft(heading_path=[t for _, t in stack], text=part))
    return drafts
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_chunker.py -q
```

Expected: 5 passed。

- [ ] **Step 5: 提交**

```bash
git add app/kb/chunker.py app/tests/test_chunker.py
git commit -m "feat: add markdown chunker with heading hierarchy and overlap"
```

---

### Task 5: Qdrant 存储模块

落实：FR-01、FR-02、FR-05、NFR-01，requirements-spec.md 第 5.2 节。

**Files:**
- Create: `app/kb/qdrant_store.py`
- Create: `app/tests/test_qdrant_store.py`

**Interfaces:**
- Consumes: `kb.chunker.chunk_sha256`。
- Produces:
  - `kb.qdrant_store.collection_name(corpus_id: str) -> str`。
  - `kb.qdrant_store.chunk_id(rel_path: str, chunk_sha: str) -> str`。
  - `kb.qdrant_store.ensure_collection(client, corpus_id: str, dim: int) -> None`。
  - `kb.qdrant_store.build_payload(corpus_id, asset: dict, chunk_sha: str, seq: int, heading_path: list[str], text: str, tags: list[str]) -> dict`。
  - `kb.qdrant_store.upsert_points(client, corpus_id: str, points: list[PointStruct]) -> None`。
  - `kb.qdrant_store.get_asset_hashes(client, corpus_id: str, rel_paths: list[str]) -> dict[str, str]`。
  - `kb.qdrant_store.list_asset_rel_paths(client, corpus_id: str) -> set[str]`（滚动取回库内全部已入库相对路径，用于识别被删除的权威源文件）。
  - `kb.qdrant_store.delete_points_by_asset(client, corpus_id: str, rel_path: str) -> None`。
  - `kb.qdrant_store.search_points(client, corpus_id, vector: list[float], filters: dict, top_k: int) -> list`。
  - `kb.qdrant_store.fetch_points(client, corpus_id: str, ids: list[str]) -> list`。
  - `asset` 字典固定字段：`rel_path: str`、`sha256: str`、`mtime: float`。

- [ ] **Step 1: 写失败测试 app/tests/test_qdrant_store.py**

```python
import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from kb.qdrant_store import (
    build_payload,
    chunk_id,
    collection_name,
    delete_points_by_asset,
    ensure_collection,
    fetch_points,
    get_asset_hashes,
    list_asset_rel_paths,
    search_points,
    upsert_points,
)

ASSET = {"rel_path": "笔记/甲.md", "sha256": "aaa", "mtime": 1700000000.0}


@pytest.fixture
def client():
    c = QdrantClient(path=":memory:")
    ensure_collection(c, "corp1", dim=4)
    return c


def _points(client, corpus_id="corp1"):
    payloads = [
        build_payload(corpus_id, ASSET, "s1", 0, ["A"], "甲正文", ["标签一"]),
        build_payload(corpus_id, ASSET, "s2", 1, ["A", "B"], "乙正文", ["标签二"]),
    ]
    return [
        PointStruct(id=chunk_id(ASSET["rel_path"], p["chunk_sha256"]), vector=[0.1, 0.2, 0.3, 0.4], payload=p)
        for p in payloads
    ]


def test_chunk_id_is_stable_and_bounded():
    cid = chunk_id("a/b.md", "sha")
    assert len(cid) == 32
    assert cid == chunk_id("a/b.md", "sha")
    assert cid != chunk_id("a/c.md", "sha")


def test_ensure_collection_is_idempotent(client):
    ensure_collection(client, "corp1", dim=4)
    assert client.collection_exists(collection_name("corp1"))


def test_upsert_and_hash_lookup(client):
    upsert_points(client, "corp1", _points(client))
    hashes = get_asset_hashes(client, "corp1", ["笔记/甲.md"])
    assert hashes == {"笔记/甲.md": "aaa"}


def test_search_filters_by_tag(client):
    upsert_points(client, "corp1", _points(client))
    hits = search_points(client, "corp1", [0.1, 0.2, 0.3, 0.4], {"tags": ["标签一"]}, top_k=5)
    assert len(hits) == 1
    assert hits[0].payload["seq"] == 0


def test_delete_by_asset(client):
    upsert_points(client, "corp1", _points(client))
    delete_points_by_asset(client, "corp1", "笔记/甲.md")
    assert get_asset_hashes(client, "corp1", ["笔记/甲.md"]) == {}


def test_list_asset_rel_paths_returns_all(client):
    upsert_points(client, "corp1", _points(client))
    other = build_payload(
        "corp1",
        {"rel_path": "笔记/乙.md", "sha256": "bbb", "mtime": 1700000001.0},
        "s3",
        0,
        ["B"],
        "丙正文",
        [],
    )
    upsert_points(
        client,
        "corp1",
        [PointStruct(id=chunk_id("笔记/乙.md", "s3"), vector=[0.1, 0.2, 0.3, 0.4], payload=other)],
    )
    assert list_asset_rel_paths(client, "corp1") == {"笔记/甲.md", "笔记/乙.md"}


def test_fetch_points_by_ids(client):
    points = _points(client)
    upsert_points(client, "corp1", points)
    got = fetch_points(client, "corp1", [points[0].id])
    assert len(got) == 1
    assert got[0].payload["chunk_sha256"] == "s1"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_qdrant_store.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'kb.qdrant_store'`。

- [ ] **Step 3: 写 app/kb/qdrant_store.py**

```python
import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)


def collection_name(corpus_id: str) -> str:
    return f"kb_{corpus_id}"


def chunk_id(rel_path: str, chunk_sha: str) -> str:
    return hashlib.sha256(f"{rel_path}::{chunk_sha}".encode("utf-8")).hexdigest()[:32]


def ensure_collection(client: QdrantClient, corpus_id: str, dim: int) -> None:
    name = collection_name(corpus_id)
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )


def build_payload(
    corpus_id: str,
    asset: dict,
    chunk_sha: str,
    seq: int,
    heading_path: list[str],
    text: str,
    tags: list[str],
) -> dict:
    return {
        "corpus_id": corpus_id,
        "asset_rel_path": asset["rel_path"],
        "asset_sha256": asset["sha256"],
        "asset_mtime": asset["mtime"],
        "seq": seq,
        "heading_path": heading_path,
        "char_len": len(text),
        "chunk_sha256": chunk_sha,
        "tags": tags,
        "text": text,
    }


def upsert_points(client: QdrantClient, corpus_id: str, points: list[PointStruct]) -> None:
    if not points:
        return
    client.upsert(collection_name=collection_name(corpus_id), points=points, wait=True)


def get_asset_hashes(client: QdrantClient, corpus_id: str, rel_paths: list[str]) -> dict[str, str]:
    if not rel_paths:
        return {}
    scroll_filter = Filter(
        must=[FieldCondition(key="asset_rel_path", match=MatchAny(any=list(rel_paths)))]
    )
    offset = None
    result: dict[str, str] = {}
    while True:
        points, offset = client.scroll(
            collection_name=collection_name(corpus_id),
            scroll_filter=scroll_filter,
            limit=1000,
            offset=offset,
            with_payload=["asset_rel_path", "asset_sha256"],
            with_vectors=False,
        )
        for point in points:
            result[point.payload["asset_rel_path"]] = point.payload["asset_sha256"]
        if offset is None:
            return result


def list_asset_rel_paths(client: QdrantClient, corpus_id: str) -> set[str]:
    offset = None
    result: set[str] = set()
    while True:
        points, offset = client.scroll(
            collection_name=collection_name(corpus_id),
            limit=1000,
            offset=offset,
            with_payload=["asset_rel_path"],
            with_vectors=False,
        )
        result.update(point.payload["asset_rel_path"] for point in points)
        if offset is None:
            return result


def delete_points_by_asset(client: QdrantClient, corpus_id: str, rel_path: str) -> None:
    scroll_filter = Filter(
        must=[FieldCondition(key="asset_rel_path", match=MatchValue(value=rel_path))]
    )
    ids: list[str] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name(corpus_id),
            scroll_filter=scroll_filter,
            limit=1000,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        ids.extend(point.id for point in points)
        if offset is None:
            break
    if ids:
        client.delete(collection_name=collection_name(corpus_id), points_selector=ids, wait=True)


def _build_filter(filters: dict) -> Filter:
    must: list = []
    if filters.get("tags"):
        must.append(FieldCondition(key="tags", match=MatchAny(any=list(filters["tags"]))))
    if filters.get("time_from") is not None or filters.get("time_to") is not None:
        must.append(
            FieldCondition(
                key="asset_mtime",
                range=Range(gte=filters.get("time_from"), lte=filters.get("time_to")),
            )
        )
    return Filter(must=must) if must else None


def search_points(
    client: QdrantClient, corpus_id: str, vector: list[float], filters: dict, top_k: int
) -> list:
    return client.query_points(
        collection_name=collection_name(corpus_id),
        query=vector,
        query_filter=_build_filter(filters or {}),
        limit=top_k,
        with_payload=True,
    ).points


def fetch_points(client: QdrantClient, corpus_id: str, ids: list[str]) -> list:
    if not ids:
        return []
    return client.retrieve(collection_name=collection_name(corpus_id), ids=ids, with_payload=True)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_qdrant_store.py -q
```

Expected: 7 passed。

- [ ] **Step 5: 提交**

```bash
git add app/kb/qdrant_store.py app/tests/test_qdrant_store.py
git commit -m "feat: add qdrant store with idempotent upsert and hash-based skip lookup"
```

---

### Task 6: Neo4j 存储与本体模块

落实：FR-01、FR-06、FR-07，requirements-spec.md 第 5.3、6.2 节，NFR-01 附则。

**Files:**
- Create: `app/kb/neo4j_store.py`
- Create: `app/kb/ontology.py`
- Create: `app/tests/test_ontology.py`
- Create: `app/tests/test_neo4j_store.py`

**Interfaces:**
- Consumes: `kb.config.Settings`。
- Produces（neo4j_store）:
  - `get_driver(settings) -> Driver`
  - `init_schema(driver) -> None`
  - `upsert_corpus(driver, corpus: dict) -> None`、`get_corpus(driver, corpus_id) -> dict | None`、`list_corpora(driver) -> list[dict]`、`delete_corpus(driver, corpus_id) -> None`
  - `write_ont_class(driver, entry: dict) -> None`、`write_ont_obj_prop(driver, entry: dict) -> None`、`write_ont_data_prop(driver, entry: dict) -> None`
  - `delete_ont_class(driver, corpus_id: str, iri: str) -> list[dict]`、`delete_ont_obj_prop(driver, corpus_id: str, iri: str) -> list[dict]`、`delete_ont_data_prop(driver, corpus_id: str, iri: str) -> None`（删除前先取回受影响实例或关系清单，由调用方转待处理队列）
  - `get_ontology(driver, corpus_id: str) -> dict`（键为 `base_iri`、`classes`、`object_properties`、`datatype_properties`）
  - `new_ont_version(driver, corpus_id: str) -> int`
  - `record_task(driver, task_id, corpus_id, status, kind="sync") -> None`、`update_task(driver, task_id, **fields) -> None`、`get_task(driver, task_id) -> dict | None`
- Produces（ontology）:
  - `ALLOWED_CHARACTERISTICS: set[str]`
  - `validate_rl(entry: dict) -> list[str]`（返回违规原因列表，空列表为通过）
  - `export_ttl(ontology: dict, path: str) -> None`（先写 `.tmp` 再原子替换）
  - `subclass_closure(classes: list[dict]) -> dict[str, set[str]]`
  - `find_violations(driver, obj_prop: dict, classes: list[dict]) -> list[dict]`
  - `check_relation_valid(classes: list[dict], obj_prop: dict, from_class_iri: str, to_class_iri: str) -> list[str]`（返回 'domain'/'range' 违规列表，空列表为通过；用于手工建关系前的写入校验）

- [ ] **Step 1: 写失败测试 app/tests/test_ontology.py**

```python
from pathlib import Path

from rdflib import Graph

from kb.ontology import check_relation_valid, export_ttl, find_violations, subclass_closure, validate_rl

CLASS_A = {
    "iri": "http://kb.local/o/c1#Project",
    "label_zh": "项目",
    "definition": "一个交付单元",
    "parent_iris": [],
    "disjoint_with": [],
}


def test_validate_rl_passes_on_complete_entry():
    assert validate_rl(CLASS_A) == []


def test_validate_rl_rejects_relative_iri():
    entry = dict(CLASS_A, iri="Project")
    assert any("IRI" in v for v in validate_rl(entry))


def test_validate_rl_requires_label_and_definition():
    entry = dict(CLASS_A, label_zh="", definition="")
    violations = validate_rl(entry)
    assert any("label_zh" in v for v in violations)
    assert any("definition" in v for v in violations)


def test_validate_rl_rejects_non_whitelisted_characteristic():
    entry = dict(CLASS_A, characteristics=["inverseOf"])
    assert any("白名单" in v for v in validate_rl(entry))


def test_validate_rl_rejects_cardinality_above_one():
    entry = dict(CLASS_A, max_cardinality=3)
    assert any("max_cardinality" in v for v in validate_rl(entry))


def test_export_ttl_is_parseable(tmp_path: Path):
    ontology = {
        "base_iri": "http://kb.local/o/c1#",
        "classes": [CLASS_A],
        "object_properties": [
            {
                "iri": "http://kb.local/o/c1#belongsTo",
                "label_zh": "属于",
                "definition": "从属关系",
                "domain_iri": "http://kb.local/o/c1#Person",
                "range_iri": "http://kb.local/o/c1#Project",
                "characteristics": ["transitive"],
            }
        ],
        "datatype_properties": [
            {
                "iri": "http://kb.local/o/c1#note",
                "label_zh": "备注",
                "definition": "自由文本",
                "domain_iri": "http://kb.local/o/c1#Project",
                "xsd_range": "http://www.w3.org/2001/XMLSchema#string",
            }
        ],
    }
    out = tmp_path / "c1.ttl"
    export_ttl(ontology, str(out))
    graph = Graph()
    graph.parse(str(out), format="turtle")
    assert len(graph) > 8


def test_export_ttl_atomic_replace_leaves_no_tmp(tmp_path: Path):
    out = tmp_path / "c1.ttl"
    export_ttl({"base_iri": "http://kb.local/o/c1#", "classes": [CLASS_A],
                "object_properties": [], "datatype_properties": []}, str(out))
    assert not (tmp_path / "c1.ttl.tmp").exists()


def test_subclass_closure_is_transitive():
    classes = [
        {"iri": "A", "parent_iris": []},
        {"iri": "B", "parent_iris": ["A"]},
        {"iri": "C", "parent_iris": ["B"]},
    ]
    closure = subclass_closure(classes)
    assert closure["C"] == {"C", "B", "A"}


def test_find_violations_flags_out_of_range():
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def data(self):
            return self.rows

    class FakeSession:
        def run(self, query, **kwargs):
            return FakeResult([{"a": "e1", "ac": "Person", "b": "e2", "bc": "Person"}])

    class FakeDriver:
        def session(self):
            return FakeSession()

    obj_prop = {
        "iri": "belongsTo",
        "domain_iri": "Person",
        "range_iri": "Project",
    }
    classes = [
        {"iri": "Person", "parent_iris": []},
        {"iri": "Project", "parent_iris": []},
    ]
    violations = find_violations(FakeDriver(), obj_prop, classes)
    assert len(violations) == 1
    assert violations[0]["reason"] == "range"


def test_check_relation_valid_domain_and_range():
    classes = [
        {"iri": "Person", "parent_iris": []},
        {"iri": "Project", "parent_iris": []},
    ]
    obj_prop = {"iri": "belongsTo", "domain_iri": "Person", "range_iri": "Project"}
    assert check_relation_valid(classes, obj_prop, "Project", "Project") == ["domain"]
    assert check_relation_valid(classes, obj_prop, "Person", "Person") == ["range"]
    assert check_relation_valid(classes, obj_prop, "Person", "Project") == []
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_ontology.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'kb.ontology'`。

- [ ] **Step 3: 写 app/kb/ontology.py**

```python
import os

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS

ALLOWED_CHARACTERISTICS = {"transitive", "symmetric", "functional", "inverse_functional"}

CHARACTERISTIC_PREDICATES = {
    "transitive": OWL.TransitiveProperty,
    "symmetric": OWL.SymmetricProperty,
    "functional": OWL.FunctionalProperty,
    "inverse_functional": OWL.InverseFunctionalProperty,
}


def validate_rl(entry: dict) -> list[str]:
    violations: list[str] = []
    if not entry.get("iri", "").startswith("http"):
        violations.append("iri 必须为完整 IRI")
    if not entry.get("label_zh"):
        violations.append("label_zh 必填")
    if not entry.get("definition"):
        violations.append("definition 必填")
    for characteristic in entry.get("characteristics", []):
        if characteristic not in ALLOWED_CHARACTERISTICS:
            violations.append(f"属性特征超出 OWL 2 RL 白名单: {characteristic}")
    for key in ("min_cardinality", "max_cardinality"):
        value = entry.get(key)
        if value is not None and value not in (0, 1):
            violations.append(f"{key} 只允许 0 或 1")
    return violations


def subclass_closure(classes: list[dict]) -> dict[str, set[str]]:
    parents = {c["iri"]: set(c.get("parent_iris", [])) for c in classes}
    closure: dict[str, set[str]] = {}
    for iri in parents:
        seen = {iri}
        stack = list(parents[iri])
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(parents.get(current, set()))
        closure[iri] = seen
    return closure


def _add_common(graph: Graph, iri: str, kind, entry: dict) -> URIRef:
    subject = URIRef(iri)
    graph.add((subject, RDF.type, kind))
    graph.add((subject, RDFS.label, Literal(entry.get("label_zh", ""), lang="zh")))
    graph.add((subject, RDFS.comment, Literal(entry.get("definition", ""))))
    return subject


def export_ttl(ontology: dict, path: str) -> None:
    graph = Graph()
    graph.bind("kb", Namespace(ontology["base_iri"]))
    for entry in ontology.get("classes", []):
        subject = _add_common(graph, entry["iri"], OWL.Class, entry)
        for parent in entry.get("parent_iris", []):
            graph.add((subject, RDFS.subClassOf, URIRef(parent)))
        for other in entry.get("disjoint_with", []):
            graph.add((subject, OWL.disjointWith, URIRef(other)))
        if entry.get("equivalent_to"):
            graph.add((subject, OWL.equivalentClass, URIRef(entry["equivalent_to"])))
    for entry in ontology.get("object_properties", []):
        subject = _add_common(graph, entry["iri"], OWL.ObjectProperty, entry)
        if entry.get("domain_iri"):
            graph.add((subject, RDFS.domain, URIRef(entry["domain_iri"])))
        if entry.get("range_iri"):
            graph.add((subject, RDFS.range, URIRef(entry["range_iri"])))
        for characteristic in entry.get("characteristics", []):
            graph.add((subject, RDF.type, CHARACTERISTIC_PREDICATES[characteristic]))
    for entry in ontology.get("datatype_properties", []):
        subject = _add_common(graph, entry["iri"], OWL.DatatypeProperty, entry)
        if entry.get("domain_iri"):
            graph.add((subject, RDFS.domain, URIRef(entry["domain_iri"])))
        if entry.get("xsd_range"):
            graph.add((subject, RDFS.range, URIRef(entry["xsd_range"])))
    tmp = f"{path}.tmp"
    graph.serialize(destination=tmp, format="turtle")
    os.replace(tmp, path)


VIOLATION_QUERY = """
MATCH (a:Entity)-[r:REL]->(b:Entity)
WHERE r.type_iri = $iri AND r.state = 'confirmed'
RETURN a.eid AS a, a.class_iri AS ac, b.eid AS b, b.class_iri AS bc
"""


def find_violations(driver, obj_prop: dict, classes: list[dict]) -> list[dict]:
    closure = subclass_closure(classes)
    domain = obj_prop.get("domain_iri")
    range_iri = obj_prop.get("range_iri")
    violations: list[dict] = []
    with driver.session() as session:
        rows = session.run(VIOLATION_QUERY, iri=obj_prop["iri"]).data()
    for row in rows:
        subject_closure = closure.get(row["ac"], {row["ac"]})
        object_closure = closure.get(row["bc"], {row["bc"]})
        if domain and domain not in subject_closure:
            violations.append(
                {"relation_type_iri": obj_prop["iri"], "from": row["a"], "to": row["b"], "reason": "domain"}
            )
        if range_iri and range_iri not in object_closure:
            violations.append(
                {"relation_type_iri": obj_prop["iri"], "from": row["a"], "to": row["b"], "reason": "range"}
            )
    return violations


def check_relation_valid(classes: list[dict], obj_prop: dict,
                         from_class_iri: str, to_class_iri: str) -> list[str]:
    closure = subclass_closure(classes)
    domain = obj_prop.get("domain_iri")
    range_iri = obj_prop.get("range_iri")
    reasons: list[str] = []
    if domain and domain not in closure.get(from_class_iri, {from_class_iri}):
        reasons.append("domain")
    if range_iri and range_iri not in closure.get(to_class_iri, {to_class_iri}):
        reasons.append("range")
    return reasons
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_ontology.py -q
```

Expected: 10 passed。

- [ ] **Step 5: 写 app/kb/neo4j_store.py**

```python
import json
import time
from uuid import uuid4

from neo4j import GraphDatabase

from kb.config import Settings

CONSTRAINT_STATEMENTS = [
    "CREATE CONSTRAINT corpus_id IF NOT EXISTS FOR (n:Corpus) REQUIRE n.corpus_id IS UNIQUE",
    "CREATE CONSTRAINT ont_class_iri IF NOT EXISTS FOR (n:OntClass) REQUIRE n.iri IS UNIQUE",
    "CREATE CONSTRAINT ont_objprop_iri IF NOT EXISTS FOR (n:OntObjProp) REQUIRE n.iri IS UNIQUE",
    "CREATE CONSTRAINT ont_dataprop_iri IF NOT EXISTS FOR (n:OntDataProp) REQUIRE n.iri IS UNIQUE",
    "CREATE CONSTRAINT entity_eid IF NOT EXISTS FOR (n:Entity) REQUIRE n.eid IS UNIQUE",
    "CREATE CONSTRAINT pending_pid IF NOT EXISTS FOR (n:PendingItem) REQUIRE n.pid IS UNIQUE",
    "CREATE CONSTRAINT opstask_id IF NOT EXISTS FOR (n:OpsTask) REQUIRE n.task_id IS UNIQUE",
]

CORPUS_FIELDS = (
    "corpus_id name subdir embedding_model vector_dim chunk_max_chars "
    "chunk_overlap ontology_prefix archived created_at"
)


def get_driver(settings: Settings):
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


def init_schema(driver) -> None:
    with driver.session() as session:
        for statement in CONSTRAINT_STATEMENTS:
            session.run(statement)


def upsert_corpus(driver, corpus: dict) -> None:
    query = f"MERGE (c:Corpus {{corpus_id: $corpus_id}}) SET c += $props"
    with driver.session() as session:
        session.run(query, corpus_id=corpus["corpus_id"], props=corpus)


def get_corpus(driver, corpus_id: str) -> dict | None:
    with driver.session() as session:
        row = session.run(
            "MATCH (c:Corpus {corpus_id: $id}) RETURN c", id=corpus_id
        ).single()
    return dict(row["c"]) if row else None


def list_corpora(driver) -> list[dict]:
    with driver.session() as session:
        return [dict(r["c"]) for r in session.run("MATCH (c:Corpus) RETURN c")]


def delete_corpus(driver, corpus_id: str) -> None:
    statements = [
        "MATCH (e:Entity {corpus_id: $id}) DETACH DELETE e",
        "MATCH (n:OntClass {corpus_id: $id}) DELETE n",
        "MATCH (n:OntObjProp {corpus_id: $id}) DELETE n",
        "MATCH (n:OntDataProp {corpus_id: $id}) DELETE n",
        "MATCH (n:OntVersion {corpus_id: $id}) DELETE n",
        "MATCH (n:PendingItem {corpus_id: $id}) DELETE n",
        "MATCH (n:OpsTask {corpus_id: $id}) DELETE n",
        "MATCH (c:Corpus {corpus_id: $id}) DELETE c",
    ]
    with driver.session() as session:
        for statement in statements:
            session.run(statement, id=corpus_id)


def _write_ontology_node(driver, label: str, corpus_id: str, entry: dict) -> None:
    props = {k: v for k, v in entry.items() if not isinstance(v, (list, dict))}
    props["corpus_id"] = corpus_id
    arrays = {k: v for k, v in entry.items() if isinstance(v, (list, dict))}
    query = f"MERGE (n:{label} {{iri: $iri}}) SET n += $props, n.arrays = $arrays"
    with driver.session() as session:
        session.run(query, iri=entry["iri"], props=props, arrays=json.dumps(arrays, ensure_ascii=False))


def write_ont_class(driver, corpus_id: str, entry: dict) -> None:
    _write_ontology_node(driver, "OntClass", corpus_id, entry)


def write_ont_obj_prop(driver, corpus_id: str, entry: dict) -> None:
    _write_ontology_node(driver, "OntObjProp", corpus_id, entry)


def write_ont_data_prop(driver, corpus_id: str, entry: dict) -> None:
    _write_ontology_node(driver, "OntDataProp", corpus_id, entry)


def _decode(node: dict) -> dict:
    out = dict(node)
    arrays = out.pop("arrays", None)
    if arrays:
        out.update(json.loads(arrays))
    return out


def get_ontology(driver, corpus_id: str) -> dict:
    with driver.session() as session:
        classes = [_decode(r["n"]) for r in session.run(
            "MATCH (n:OntClass {corpus_id: $id}) RETURN n", id=corpus_id)]
        obj_props = [_decode(r["n"]) for r in session.run(
            "MATCH (n:OntObjProp {corpus_id: $id}) RETURN n", id=corpus_id)]
        data_props = [_decode(r["n"]) for r in session.run(
            "MATCH (n:OntDataProp {corpus_id: $id}) RETURN n", id=corpus_id)]
        corpus = session.run(
            "MATCH (c:Corpus {corpus_id: $id}) RETURN c.ontology_prefix AS p", id=corpus_id
        ).single()
    prefix = corpus["p"] if corpus else corpus_id
    return {
        "base_iri": f"http://kb.local/o/{prefix}#",
        "classes": classes,
        "object_properties": obj_props,
        "datatype_properties": data_props,
    }


def new_ont_version(driver, corpus_id: str) -> int:
    with driver.session() as session:
        row = session.run(
            """
            MATCH (c:Corpus {corpus_id: $id})
            OPTIONAL MATCH (v:OntVersion {corpus_id: $id})
            WITH c, coalesce(max(v.seq), 0) + 1 AS seq
            CREATE (:OntVersion {corpus_id: $id, seq: seq, exported_at: $now})
            RETURN seq
            """,
            id=corpus_id,
            now=time.time(),
        ).single()
    return row["seq"]


def record_task(driver, task_id: str, corpus_id: str, status: str, kind: str = "sync") -> None:
    with driver.session() as session:
        session.run(
            """
            CREATE (t:OpsTask {task_id: $task_id, corpus_id: $corpus_id, kind: $kind,
                               status: $status, started_at: $now,
                               doc_total: 0, doc_changed: 0, doc_removed: 0, chunks: 0,
                               tokens: 0, embed_retries: 0, cost_estimate: 0.0, proposals: 0,
                               error_code: ''})
            """,
            task_id=task_id, corpus_id=corpus_id, kind=kind, status=status, now=time.time(),
        )


def update_task(driver, task_id: str, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"t.{key} = ${key}" for key in fields)
    with driver.session() as session:
        session.run(f"MATCH (t:OpsTask {{task_id: $task_id}}) SET {sets}", task_id=task_id, **fields)


def get_task(driver, task_id: str) -> dict | None:
    with driver.session() as session:
        row = session.run("MATCH (t:OpsTask {task_id: $id}) RETURN t", id=task_id).single()
    return dict(row["t"]) if row else None


def new_pending_id() -> str:
    return uuid4().hex


def delete_ont_class(driver, corpus_id: str, iri: str) -> list[dict]:
    with driver.session() as session:
        rows = session.run(
            """
            MATCH (e:Entity {corpus_id: $id})-[:INSTANCE_OF]->(c:OntClass {iri: $iri})
            RETURN e.eid AS eid, e.label AS label
            """,
            id=corpus_id, iri=iri,
        ).data()
        session.run(
            "MATCH (n:OntClass {corpus_id: $id, iri: $iri}) DETACH DELETE n",
            id=corpus_id, iri=iri,
        )
    return rows


def delete_ont_obj_prop(driver, corpus_id: str, iri: str) -> list[dict]:
    with driver.session() as session:
        rows = session.run(
            """
            MATCH (a:Entity)-[r:REL {type_iri: $iri, state: 'confirmed'}]->(b:Entity)
            WHERE a.corpus_id = $id
            RETURN a.eid AS from_eid, a.label AS from_label, b.eid AS to_eid, b.label AS to_label
            """,
            id=corpus_id, iri=iri,
        ).data()
        session.run("MATCH ()-[r:REL {type_iri: $iri}]->() DELETE r", iri=iri)
        session.run("MATCH (n:OntObjProp {corpus_id: $id, iri: $iri}) DELETE n", id=corpus_id, iri=iri)
    return rows


def delete_ont_data_prop(driver, corpus_id: str, iri: str) -> None:
    with driver.session() as session:
        session.run(
            "MATCH (n:OntDataProp {corpus_id: $id, iri: $iri}) DELETE n",
            id=corpus_id, iri=iri,
        )
```

- [ ] **Step 6: 写集成测试 app/tests/test_neo4j_store.py**

```python
import pytest

from kb.config import get_settings
from kb.neo4j_store import (
    delete_corpus,
    get_corpus,
    get_driver,
    get_ontology,
    init_schema,
    list_corpora,
    new_ont_version,
    record_task,
    update_task,
    upsert_corpus,
    write_ont_class,
)

CORPUS = {
    "corpus_id": "c-test",
    "name": "测试库",
    "subdir": "acceptance",
    "embedding_model": "text-embedding-v4",
    "vector_dim": 1024,
    "chunk_max_chars": 700,
    "chunk_overlap": 60,
    "ontology_prefix": "ctest",
    "archived": False,
    "created_at": 0.0,
}


@pytest.fixture
def driver():
    settings = get_settings()
    if not settings.neo4j_password:
        pytest.skip("需要 .env 中的 NEO4J_PASSWORD")
    drv = get_driver(settings)
    init_schema(drv)
    yield drv
    delete_corpus(drv, "c-test")
    drv.close()


@pytest.mark.integration
def test_corpus_roundtrip(driver):
    upsert_corpus(driver, CORPUS)
    assert get_corpus(driver, "c-test")["subdir"] == "acceptance"
    assert any(c["corpus_id"] == "c-test" for c in list_corpora(driver))


@pytest.mark.integration
def test_ontology_write_and_read_back(driver):
    upsert_corpus(driver, CORPUS)
    write_ont_class(
        driver,
        "c-test",
        {
            "iri": "http://kb.local/o/ctest#Project",
            "label_zh": "项目",
            "definition": "一个交付单元",
            "parent_iris": [],
            "disjoint_with": [],
            "aliases": ["项目组"],
        },
    )
    ontology = get_ontology(driver, "c-test")
    assert ontology["base_iri"] == "http://kb.local/o/ctest#"
    assert ontology["classes"][0]["aliases"] == ["项目组"]


@pytest.mark.integration
def test_ont_version_increments(driver):
    upsert_corpus(driver, CORPUS)
    first = new_ont_version(driver, "c-test")
    second = new_ont_version(driver, "c-test")
    assert second == first + 1


@pytest.mark.integration
def test_task_record_and_update(driver):
    record_task(driver, "t1", "c-test", "running")
    update_task(driver, "t1", status="done", tokens=120, cost_estimate=0.06)
    from kb.neo4j_store import get_task

    task = get_task(driver, "t1")
    assert task["status"] == "done" and task["tokens"] == 120
```

- [ ] **Step 7: 运行集成测试**

```bash
cd app && set -a && . ../.env && set +a && NEO4J_URI=bolt://127.0.0.1:7687 NEO4J_PASSWORD="$NEO4J_PASSWORD" .venv/Scripts/python -m pytest tests/test_neo4j_store.py -q
```

Expected: 4 passed。

- [ ] **Step 8: 提交**

```bash
git add app/kb/neo4j_store.py app/kb/ontology.py app/tests/test_ontology.py app/tests/test_neo4j_store.py
git commit -m "feat: add neo4j store and owl 2 rl ontology validation with ttl export"
```

---

### Task 7: 提案生成与待处理队列

落实：FR-08、FR-09，requirements-spec.md 第 5.3 节 PendingItem 与 Entity。

**Files:**
- Create: `app/kb/proposals.py`
- Create: `app/tests/test_proposals.py`

**Interfaces:**
- Consumes: `kb.neo4j_store.get_driver`、`new_pending_id`。
- Produces:
  - `kb.proposals.get_classes_with_aliases(driver, corpus_id: str) -> list[dict]`（元素含 `iri`、`label_zh`、`aliases`）
  - `kb.proposals.entity_id(class_iri: str, label: str) -> str`
  - `kb.proposals.generate_entity_proposals(driver, corpus_id: str, chunks: list[dict]) -> int`（chunk 字典键：`asset_rel_path`、`seq`、`chunk_sha256`、`text`）
  - `kb.proposals.create_pending(driver, corpus_id: str, kind: str, payload: dict) -> str`
  - `kb.proposals.list_pending(driver, corpus_id: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]`
  - `kb.proposals.resolve_pending(driver, pid: str, action: str, new_class_iri: str | None = None) -> dict`（action ∈ confirm、reject、retype）
  - `kb.proposals.ensure_entity(driver, corpus_id, label, class_iri, anchor, ont_version: int) -> str`
  - `kb.proposals.find_entities_by_anchor_rel_path(driver, corpus_id: str, rel_path: str) -> list[dict]`（元素含 `eid`、`label`、`anchors`，用于删除文件后定位受影响实体）
  - `kb.proposals.split_entity(driver, eid: str, new_label: str, anchors: list[dict], class_iri: str | None = None) -> dict`（返回 `eid`、`src_anchors`、`new_anchors`；锚点子集必须非空且为源实体锚点真子集）

- [ ] **Step 1: 写失败测试 app/tests/test_proposals.py**

```python
import pytest

from kb.config import get_settings
from kb.neo4j_store import delete_corpus, get_driver, init_schema, upsert_corpus, write_ont_class
from kb.proposals import (
    create_pending,
    ensure_entity,
    entity_id,
    find_entities_by_anchor_rel_path,
    generate_entity_proposals,
    list_pending,
    resolve_pending,
    split_entity,
)

CORPUS = {
    "corpus_id": "c-prop", "name": "提案库", "subdir": "acceptance",
    "embedding_model": "text-embedding-v4", "vector_dim": 1024,
    "chunk_max_chars": 700, "chunk_overlap": 60, "ontology_prefix": "cprop",
    "archived": False, "created_at": 0.0,
}
CLASS = {
    "iri": "http://kb.local/o/cprop#Project", "label_zh": "项目",
    "definition": "一个交付单元", "parent_iris": [], "disjoint_with": [],
    "aliases": ["项目组"],
}
CHUNKS = [
    {"asset_rel_path": "a.md", "seq": 0, "chunk_sha256": "s0", "text": "本项目组由三人组成"},
    {"asset_rel_path": "b.md", "seq": 0, "chunk_sha256": "s1", "text": "无关内容"},
    {"asset_rel_path": "c.md", "seq": 2, "chunk_sha256": "s2", "text": "项目组例会"},
]


@pytest.fixture
def driver():
    settings = get_settings()
    if not settings.neo4j_password:
        pytest.skip("需要 .env 中的 NEO4J_PASSWORD")
    drv = get_driver(settings)
    init_schema(drv)
    upsert_corpus(drv, CORPUS)
    write_ont_class(drv, "c-prop", CLASS)
    yield drv
    delete_corpus(drv, "c-prop")
    drv.close()


@pytest.mark.integration
def test_entity_id_is_deterministic():
    assert entity_id("http://kb.local/o/cprop#Project", "项目组") == entity_id("http://kb.local/o/cprop#Project", "项目组")


@pytest.mark.integration
def test_alias_match_creates_two_proposals(driver):
    assert generate_entity_proposals(driver, "c-prop", CHUNKS) == 2
    assert len(list_pending(driver, "c-prop")) == 2


@pytest.mark.integration
def test_confirm_merges_anchors_from_multiple_files(driver):
    generate_entity_proposals(driver, "c-prop", CHUNKS)
    items = list_pending(driver, "c-prop")
    first = resolve_pending(driver, items[0]["pid"], "confirm")
    second = resolve_pending(driver, items[1]["pid"], "confirm")
    assert first["eid"] == second["eid"]
    assert second["anchor_count"] == 2


@pytest.mark.integration
def test_reject_removes_item(driver):
    create_pending(driver, "c-prop", "proposal", {"label": "临时"})
    items = list_pending(driver, "c-prop")
    resolve_pending(driver, items[0]["pid"], "reject")
    assert all(i["status"] != "open" for i in list_pending(driver, "c-prop", include_closed=True))


@pytest.mark.integration
def test_ensure_entity_keeps_single_node(driver):
    anchor = {"rel_path": "d.md", "seq": 0, "sha256": "s9"}
    eid = ensure_entity(driver, "c-prop", "项目甲", CLASS["iri"], anchor, ont_version=1)
    ensure_entity(driver, "c-prop", "项目甲", CLASS["iri"], anchor, ont_version=1)
    with driver.session() as session:
        count = session.run("MATCH (e:Entity {eid: $eid}) RETURN count(e) AS n", eid=eid).single()["n"]
    assert count == 1


@pytest.mark.integration
def test_find_entities_by_anchor_rel_path(driver):
    anchor = {"rel_path": "e.md", "seq": 0, "sha256": "s7"}
    ensure_entity(driver, "c-prop", "项目乙", CLASS["iri"], anchor, ont_version=1)
    found = find_entities_by_anchor_rel_path(driver, "c-prop", "e.md")
    assert len(found) == 1
    assert found[0]["eid"] == entity_id(CLASS["iri"], "项目乙")


@pytest.mark.integration
def test_split_entity_moves_anchor_subset(driver):
    a1 = {"rel_path": "f1.md", "seq": 0, "sha256": "s8"}
    a2 = {"rel_path": "f2.md", "seq": 0, "sha256": "s9"}
    eid = ensure_entity(driver, "c-prop", "项目丙", CLASS["iri"], a1, ont_version=1)
    ensure_entity(driver, "c-prop", "项目丙", CLASS["iri"], a2, ont_version=1)
    result = split_entity(driver, eid, "项目丙-子", [a1])
    assert result["src_anchors"] == 1
    assert result["new_anchors"] == 1
    with driver.session() as session:
        rows = session.run(
            "MATCH (e:Entity {corpus_id: 'c-prop'}) RETURN size(e.anchors) AS n ORDER BY n"
        ).data()
    assert [row["n"] for row in rows] == [1, 1]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_proposals.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'kb.proposals'`。

- [ ] **Step 3: 写 app/kb/proposals.py**

```python
import hashlib
import json

from kb.neo4j_store import new_pending_id


def get_classes_with_aliases(driver, corpus_id: str) -> list[dict]:
    query = """
    MATCH (c:OntClass {corpus_id: $corpus_id})
    RETURN c.iri AS iri, c.label_zh AS label_zh, c.arrays AS arrays
    """
    with driver.session() as session:
        rows = session.run(query, corpus_id=corpus_id).data()
    classes = []
    for row in rows:
        arrays = json.loads(row["arrays"]) if row["arrays"] else {}
        classes.append(
            {"iri": row["iri"], "label_zh": row["label_zh"], "aliases": arrays.get("aliases", [])}
        )
    return classes


def entity_id(class_iri: str, label: str) -> str:
    return hashlib.sha256(f"{class_iri}::{label}".encode("utf-8")).hexdigest()[:24]


def create_pending(driver, corpus_id: str, kind: str, payload: dict) -> str:
    pid = new_pending_id()
    with driver.session() as session:
        session.run(
            """
            CREATE (p:PendingItem {pid: $pid, corpus_id: $corpus_id, kind: $kind,
                                   payload: $payload, attempts: 0,
                                   last_error_code: '', status: 'open', created_at: timestamp()})
            """,
            pid=pid, corpus_id=corpus_id, kind=kind, payload=json.dumps(payload, ensure_ascii=False),
        )
    return pid


def list_pending(driver, corpus_id: str | None = None, limit: int = 50, offset: int = 0,
                 include_closed: bool = False) -> list[dict]:
    query = "MATCH (p:PendingItem) WHERE ($corpus_id IS NULL OR p.corpus_id = $corpus_id)"
    if not include_closed:
        query += " AND p.status = 'open'"
    query += " RETURN p ORDER BY p.created_at DESC SKIP $offset LIMIT $limit"
    with driver.session() as session:
        rows = session.run(query, corpus_id=corpus_id, offset=offset, limit=limit).data()
    out = []
    for row in rows:
        node = dict(row["p"])
        node["payload"] = json.loads(node["payload"]) if node.get("payload") else {}
        out.append(node)
    return out


def ensure_entity(driver, corpus_id: str, label: str, class_iri: str, anchor: dict,
                  ont_version: int) -> str:
    eid = entity_id(class_iri, label)
    with driver.session() as session:
        session.run(
            """
            MERGE (e:Entity {eid: $eid})
            ON CREATE SET e.corpus_id = $corpus_id, e.label = $label, e.class_iri = $class_iri,
                          e.aliases = [], e.anchors = [$anchor], e.ont_version = $version
            ON MATCH SET e.anchors = CASE WHEN $anchor IN e.anchors THEN e.anchors
                                          ELSE e.anchors + $anchor END,
                         e.ont_version = $version
            WITH e
            MERGE (c:OntClass {iri: $class_iri})
            MERGE (e)-[:INSTANCE_OF]->(c)
            """,
            eid=eid, corpus_id=corpus_id, label=label, class_iri=class_iri,
            anchor=anchor, version=ont_version,
        )
    return eid


def _pending_payload(driver, pid: str) -> dict:
    with driver.session() as session:
        row = session.run(
            "MATCH (p:PendingItem {pid: $pid}) RETURN p.payload AS payload, p.kind AS kind, p.corpus_id AS corpus_id",
            pid=pid,
        ).single()
    if row is None:
        raise KeyError(pid)
    return {
        "kind": row["kind"],
        "corpus_id": row["corpus_id"],
        "payload": json.loads(row["payload"]) if row["payload"] else {},
    }


def resolve_pending(driver, pid: str, action: str, new_class_iri: str | None = None) -> dict:
    record = _pending_payload(driver, pid)
    payload = record["payload"]
    if action == "reject":
        status = "rejected"
        eid = ""
    elif action == "retype":
        if not new_class_iri:
            raise ValueError("retype 需要 new_class_iri")
        payload["class_iri"] = new_class_iri
        status = "open"
        eid = ""
    else:
        status = "confirmed"
        eid = ensure_entity(
            driver,
            record["corpus_id"],
            payload.get("label", payload.get("term", "")),
            payload.get("class_iri", new_class_iri or ""),
            payload.get("anchor", {}),
            ont_version=payload.get("ont_version", 0),
        )
    with driver.session() as session:
        session.run(
            "MATCH (p:PendingItem {pid: $pid}) SET p.status = $status", pid=pid, status=status
        )
    anchor_count = 0
    if eid:
        with driver.session() as session:
            anchor_count = session.run(
                "MATCH (e:Entity {eid: $eid}) RETURN size(e.anchors) AS n", eid=eid
            ).single()["n"]
    return {"pid": pid, "action": action, "status": status, "eid": eid, "anchor_count": anchor_count}


def generate_entity_proposals(driver, corpus_id: str, chunks: list[dict]) -> int:
    classes = get_classes_with_aliases(driver, corpus_id)
    created = 0
    for ontology_class in classes:
        terms = [ontology_class["label_zh"]] + list(ontology_class.get("aliases", []))
        for chunk in chunks:
            matched = next((term for term in terms if term and term in chunk["text"]), None)
            if matched is None:
                continue
            create_pending(
                driver,
                corpus_id,
                "proposal",
                {
                    "class_iri": ontology_class["iri"],
                    "term": matched,
                    "label": matched,
                    "anchor": {
                        "rel_path": chunk["asset_rel_path"],
                        "seq": chunk["seq"],
                        "sha256": chunk["chunk_sha256"],
                    },
                },
            )
            created += 1
    return created


def find_entities_by_anchor_rel_path(driver, corpus_id: str, rel_path: str) -> list[dict]:
    query = """
    MATCH (e:Entity {corpus_id: $corpus_id})
    WHERE any(a IN e.anchors WHERE a.rel_path = $rel_path)
    RETURN e.eid AS eid, e.label AS label,
           [a IN e.anchors WHERE a.rel_path = $rel_path] AS anchors
    """
    with driver.session() as session:
        return session.run(query, corpus_id=corpus_id, rel_path=rel_path).data()


def split_entity(driver, eid: str, new_label: str, anchors: list[dict],
                 class_iri: str | None = None) -> dict:
    with driver.session() as session:
        row = session.run("MATCH (src:Entity {eid: $eid}) RETURN src", eid=eid).single()
        if row is None:
            raise KeyError(eid)
        src = dict(row["src"])
        src_anchors = list(src.get("anchors") or [])
        if not anchors:
            raise ValueError("anchors 不能为空")
        if any(a not in src_anchors for a in anchors):
            raise ValueError("anchors 必须为源实体锚点的子集")
        if len(src_anchors) - len(anchors) < 1:
            raise ValueError("拆分后源实体至少保留一个锚点")
        target_class = class_iri or src["class_iri"]
        new_eid = entity_id(target_class, new_label)
        result = session.run(
            """
            MATCH (src:Entity {eid: $eid})
            SET src.anchors = [a IN src.anchors WHERE NOT a IN $anchors]
            CREATE (n:Entity {eid: $new_eid, corpus_id: src.corpus_id, label: $label,
                              class_iri: $class_iri, aliases: [], anchors: $anchors,
                              ont_version: src.ont_version})
            WITH n, src
            MATCH (c:OntClass {iri: $class_iri})
            MERGE (n)-[:INSTANCE_OF]->(c)
            RETURN size(src.anchors) AS src_anchors, size(n.anchors) AS new_anchors
            """,
            eid=eid, new_eid=new_eid, label=new_label, class_iri=target_class,
            anchors=anchors,
        ).single()
    return {"eid": new_eid, "src_anchors": result["src_anchors"], "new_anchors": result["new_anchors"]}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd app && set -a && . ../.env && set +a && .venv/Scripts/python -m pytest tests/test_proposals.py -q
```

Expected: 7 passed。

- [ ] **Step 5: 提交**

```bash
git add app/kb/proposals.py app/tests/test_proposals.py
git commit -m "feat: add alias-based entity proposals and pending queue resolution"
```

---

### Task 8: 同步任务与定时轮询

落实：FR-02、FR-11、NFR-01、NFR-02、NFR-05、NFR-09，requirements-spec.md 第 6.1 节。

**Files:**
- Create: `app/kb/sync.py`
- Create: `app/kb/worker.py`
- Create: `app/tests/test_sync.py`

**Interfaces:**
- Consumes: `kb.chunker`、`kb.embed.embed_with_retry`、`kb.qdrant_store`、`kb.neo4j_store`、`kb.proposals.generate_entity_proposals` 与 `create_pending`。
- Produces:
  - `kb.sync.SUFFIXES: set[str]`
  - `kb.sync.file_sha256(path: Path) -> str`
  - `kb.sync.scan_assets(root: Path, targets: list[str] | None = None) -> list[dict]`
  - `async kb.sync.run_sync(settings, corpus_id: str, scope: str = "all", file_path: str | None = None) -> str`（返回 task_id；一次同步内文档级并行准备、切片级批量嵌入）
  - `async kb.sync.run_rebuild(settings, corpus_id: str, mode: str) -> str`（mode ∈ `structure`、`reembed`，返回 task_id；structure 不调用嵌入服务，reembed 删除 collection 后全量重嵌入）
  - `async kb.sync.estimate_rebuild(settings, corpus_id: str) -> dict`（返回 `chunks`、`embed_requests`、`cost_estimate`）
  - `kb.worker.poll_minutes(interval: int) -> set[int]`
  - `kb.worker.WorkerSettings`（arq 入口，`arq kb.worker.WorkerSettings`）
  - 任务状态取值：`running`、`done`、`partial`、`failed`；任务 kind 取值：`sync`、`rebuild`。

- [ ] **Step 1: 写失败测试 app/tests/test_sync.py**

```python
import json

import httpx
import pytest
import respx
from qdrant_client import QdrantClient

from kb.config import Settings, get_settings
from kb.neo4j_store import delete_corpus, get_driver, get_task, init_schema, upsert_corpus
from kb.proposals import ensure_entity, list_pending
from kb.qdrant_store import collection_name
from kb.sync import file_sha256, run_sync, scan_assets

CORPUS = {
    "corpus_id": "c-sync", "name": "同步库", "subdir": "acc",
    "embedding_model": "text-embedding-v4", "vector_dim": 4,
    "chunk_max_chars": 700, "chunk_overlap": 60, "ontology_prefix": "csync",
    "archived": False, "created_at": 0.0,
}

EMBED_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"


def _embed_response(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "data": [
                {"embedding": [0.1, 0.2, 0.3, 0.4], "index": index}
                for index in range(len(body["input"]))
            ],
            "usage": {"total_tokens": 4 * len(body["input"])},
        },
    )


def _fake_embedding_route():
    return respx.post(EMBED_URL).mock(side_effect=_embed_response)


def get_settings_for(tmp_path) -> Settings:
    return get_settings().model_copy(update={"kb_corpus_root": str(tmp_path)})


def test_scan_assets_finds_md_and_txt(tmp_path):
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "a.md").write_text("# A\n甲", encoding="utf-8")
    (tmp_path / "acc" / "b.txt").write_text("乙", encoding="utf-8")
    (tmp_path / "acc" / "c.pdf").write_bytes(b"%PDF")
    assets = scan_assets(tmp_path / "acc")
    assert [a["rel_path"] for a in assets] == ["a.md", "b.txt"]
    assert assets[0]["sha256"] == file_sha256(tmp_path / "acc" / "a.md")


def test_scan_assets_targets_filter(tmp_path):
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "a.md").write_text("# A\n甲", encoding="utf-8")
    (tmp_path / "acc" / "b.md").write_text("# B\n乙", encoding="utf-8")
    assert [a["rel_path"] for a in scan_assets(tmp_path / "acc", ["b.md"])] == ["b.md"]


@respx.mock
@pytest.mark.integration
async def test_run_sync_is_idempotent(tmp_path):
    (tmp_path / "acc").mkdir()
    note = tmp_path / "acc" / "a.md"
    note.write_text("# 标题\n项目组甲的说明文字", encoding="utf-8")

    settings = get_settings_for(tmp_path)
    route = _fake_embedding_route()
    driver = get_driver(settings)
    init_schema(driver)
    upsert_corpus(driver, CORPUS)

    task_first = await run_sync(settings, "c-sync")
    calls_first = route.call_count
    task_second = await run_sync(settings, "c-sync")
    calls_second = route.call_count - calls_first

    first = get_task(driver, task_first)
    second = get_task(driver, task_second)
    assert first["status"] == "done" and first["doc_changed"] == 1
    assert calls_second == 0
    assert second["doc_changed"] == 0 and second["tokens"] == 0

    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    info = client.get_collection(collection_name("c-sync"))
    assert info.points_count == 1

    note.write_text("# 标题\n项目组甲的说明文字（已修订）", encoding="utf-8")
    task_third = await run_sync(settings, "c-sync")
    third = get_task(driver, task_third)
    assert third["doc_changed"] == 1
    assert client.get_collection(collection_name("c-sync")).points_count == 1

    delete_corpus(driver, "c-sync")
    client.delete_collection(collection_name("c-sync"))
    driver.close()
    client.close()


@respx.mock
@pytest.mark.integration
async def test_run_sync_removes_deleted_asset_and_queues_violation(tmp_path):
    (tmp_path / "acc").mkdir()
    first = tmp_path / "acc" / "a.md"
    second = tmp_path / "acc" / "b.md"
    first.write_text("# 甲\n项目组甲", encoding="utf-8")
    second.write_text("# 乙\n项目组乙", encoding="utf-8")

    settings = get_settings_for(tmp_path)
    _fake_embedding_route()
    driver = get_driver(settings)
    init_schema(driver)
    upsert_corpus(driver, CORPUS)
    ensure_entity(
        driver,
        "c-sync",
        "项目组乙",
        "http://kb.local/o/csync#Project",
        {"rel_path": "b.md", "seq": 0, "sha256": "s-b"},
        ont_version=1,
    )

    await run_sync(settings, "c-sync")
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    assert client.get_collection(collection_name("c-sync")).points_count == 2

    second.unlink()
    task = await run_sync(settings, "c-sync")
    record = get_task(driver, task)
    assert record["doc_removed"] == 1
    assert client.get_collection(collection_name("c-sync")).points_count == 1
    items = list_pending(driver, "c-sync")
    assert any(i["payload"].get("reason") == "source_file_deleted" for i in items)

    delete_corpus(driver, "c-sync")
    client.delete_collection(collection_name("c-sync"))
    driver.close()
    client.close()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_sync.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'kb.sync'`。

- [ ] **Step 3: 写 app/kb/sync.py**

```python
import hashlib
import asyncio
import time
from pathlib import Path
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from kb.chunker import chunk_markdown, chunk_sha256, extract_frontmatter
from kb.config import Settings
from kb.embed import EmbedError, embed_with_retry
from kb.neo4j_store import (
    get_corpus,
    get_driver,
    init_schema,
    list_corpora,
    record_task,
    update_task,
)
from kb.proposals import (
    create_pending,
    find_entities_by_anchor_rel_path,
    generate_entity_proposals,
)
from kb.qdrant_store import (
    build_payload,
    chunk_id,
    collection_name,
    delete_points_by_asset,
    ensure_collection,
    fetch_points,
    get_asset_hashes,
    list_asset_rel_paths,
    upsert_points,
)

SUFFIXES = {".md", ".markdown", ".txt"}

EMBED_CONCURRENCY = 4


def qdrant_client(settings: Settings) -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_assets(root: Path, targets: list[str] | None = None) -> list[dict]:
    assets = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        rel_path = path.relative_to(root).as_posix()
        if targets and rel_path not in targets:
            continue
        assets.append(
            {
                "rel_path": rel_path,
                "sha256": file_sha256(path),
                "mtime": path.stat().st_mtime,
            }
        )
    return assets


def _prepare_asset(corpus: dict, asset: dict, root: Path) -> list[dict]:
    text = (root / asset["rel_path"]).read_text(encoding="utf-8")
    meta, body = extract_frontmatter(text)
    tags = meta.get("tags") or []
    drafts = chunk_markdown(
        body,
        max_chars=corpus["chunk_max_chars"],
        overlap=corpus["chunk_overlap"],
    )
    return [
        {
            "id": chunk_id(asset["rel_path"], chunk_sha256(draft.text)),
            "text": draft.text,
            "payload": build_payload(
                corpus["corpus_id"],
                asset,
                chunk_sha256(draft.text),
                seq,
                draft.heading_path,
                draft.text,
                tags,
            ),
        }
        for seq, draft in enumerate(drafts)
    ]


async def _sync_assets(settings, driver, client, corpus, task_id, targets) -> None:
    corpus_id = corpus["corpus_id"]
    root = Path(settings.kb_corpus_root) / corpus["subdir"]

    assets = scan_assets(root, targets)
    existing = get_asset_hashes(client, corpus_id, [a["rel_path"] for a in assets])
    changed = [a for a in assets if existing.get(a["rel_path"]) != a["sha256"]]

    removed: list[str] = []
    if targets is None:
        stored = list_asset_rel_paths(client, corpus_id)
        removed = sorted(stored - {a["rel_path"] for a in assets})
        for rel_path in removed:
            delete_points_by_asset(client, corpus_id, rel_path)
            for entity in find_entities_by_anchor_rel_path(driver, corpus_id, rel_path):
                create_pending(
                    driver,
                    corpus_id,
                    "violation",
                    {
                        "entity_eid": entity["eid"],
                        "entity_label": entity["label"],
                        "anchors": entity["anchors"],
                        "reason": "source_file_deleted",
                    },
                )

    if targets:
        for asset in changed:
            delete_points_by_asset(client, corpus_id, asset["rel_path"])

    prepared_groups = await asyncio.gather(
        *(
            asyncio.to_thread(_prepare_asset, corpus, asset, root)
            for asset in changed
        )
    )
    prepared = [item for group in prepared_groups for item in group]

    semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)
    tokens_total = 0
    retries_total = 0
    failed_batches = 0

    async def embed_batch(batch: list[dict]) -> None:
        nonlocal tokens_total, retries_total, failed_batches
        async with semaphore:
            try:
                vectors, tokens, retries = await embed_with_retry(
                    settings, [item["text"] for item in batch]
                )
            except EmbedError as exc:
                failed_batches += 1
                create_pending(
                    driver,
                    corpus_id,
                    "embed_failed",
                    {
                        "error_code": exc.code.value,
                        "message": exc.message[:200],
                        "chunk_ids": [item["id"] for item in batch],
                    },
                )
                return
        tokens_total += tokens
        retries_total += retries
        upsert_points(
            client,
            corpus_id,
            [
                PointStruct(id=item["id"], vector=vector, payload=item["payload"])
                for item, vector in zip(batch, vectors)
            ],
        )

    batches = [
        prepared[start:start + settings.kb_embed_batch]
        for start in range(0, len(prepared), settings.kb_embed_batch)
    ]
    await asyncio.gather(*(embed_batch(batch) for batch in batches))

    proposals_total = 0
    for group in prepared_groups:
        proposals_total += generate_entity_proposals(
            driver,
            corpus_id,
            [
                {
                    "asset_rel_path": item["payload"]["asset_rel_path"],
                    "seq": item["payload"]["seq"],
                    "chunk_sha256": item["payload"]["chunk_sha256"],
                    "text": item["text"],
                }
                for item in group
            ],
        )

    update_task(
        driver,
        task_id,
        status="partial" if failed_batches else "done",
        doc_total=len(assets),
        doc_changed=len(changed),
        doc_removed=len(removed),
        chunks=len(prepared),
        tokens=tokens_total,
        embed_retries=retries_total,
        cost_estimate=round(
            tokens_total / 1000 * settings.kb_embed_price_per_1k_tokens, 6
        ),
        proposals=proposals_total,
        error_code="EMBED_PARTIAL" if failed_batches else "",
        finished_at=time.time(),
    )


async def run_sync(settings: Settings, corpus_id: str, scope: str = "all",
                   file_path: str | None = None) -> str:
    task_id = uuid4().hex
    driver = get_driver(settings)
    client = qdrant_client(settings)
    try:
        init_schema(driver)
        corpus = get_corpus(driver, corpus_id)
        if corpus is None:
            raise ValueError(f"corpus not found: {corpus_id}")
        record_task(driver, task_id, corpus_id, "running")
        ensure_collection(client, corpus_id, corpus["vector_dim"])
        targets = [file_path] if scope == "file" and file_path else None
        await _sync_assets(settings, driver, client, corpus, task_id, targets)
    except Exception:
        update_task(driver, task_id, status="failed", error_code="INTERNAL", finished_at=time.time())
        raise
    finally:
        driver.close()
        client.close()
    return task_id


async def run_rebuild(settings: Settings, corpus_id: str, mode: str) -> str:
    task_id = uuid4().hex
    driver = get_driver(settings)
    client = qdrant_client(settings)
    try:
        init_schema(driver)
        corpus = get_corpus(driver, corpus_id)
        if corpus is None:
            raise ValueError(f"corpus not found: {corpus_id}")
        if mode not in ("structure", "reembed"):
            raise ValueError(f"unknown rebuild mode: {mode}")
        record_task(driver, task_id, corpus_id, "running", kind="rebuild")
        if mode == "reembed":
            client.delete_collection(collection_name(corpus_id))
            ensure_collection(client, corpus_id, corpus["vector_dim"])
            await _sync_assets(settings, driver, client, corpus, task_id, None)
        else:
            root = Path(settings.kb_corpus_root) / corpus["subdir"]
            fixed = 0
            for asset in scan_assets(root):
                prepared = _prepare_asset(corpus, asset, root)
                existing = {
                    point.id: point
                    for point in fetch_points(client, corpus_id, [item["id"] for item in prepared])
                }
                points = []
                for item in prepared:
                    point = existing.get(item["id"])
                    if point is None:
                        create_pending(
                            driver,
                            corpus_id,
                            "violation",
                            {"chunk_id": item["id"], "reason": "structure_rebuild_missing_vector"},
                        )
                        continue
                    points.append(
                        PointStruct(id=item["id"], vector=point.vector, payload=item["payload"])
                    )
                upsert_points(client, corpus_id, points)
                fixed += len(points)
            update_task(
                driver,
                task_id,
                status="done",
                doc_total=len(scan_assets(root)),
                chunks=fixed,
                tokens=0,
                embed_retries=0,
                cost_estimate=0.0,
                finished_at=time.time(),
            )
    except Exception:
        update_task(driver, task_id, status="failed", error_code="INTERNAL", finished_at=time.time())
        raise
    finally:
        driver.close()
        client.close()
    return task_id


async def estimate_rebuild(settings: Settings, corpus_id: str) -> dict:
    driver = get_driver(settings)
    try:
        corpus = get_corpus(driver, corpus_id)
        if corpus is None:
            raise ValueError(f"corpus not found: {corpus_id}")
    finally:
        driver.close()
    root = Path(settings.kb_corpus_root) / corpus["subdir"]
    chunks_total = 0
    chars_total = 0
    for asset in scan_assets(root):
        meta, body = extract_frontmatter((root / asset["rel_path"]).read_text(encoding="utf-8"))
        chunks_total += len(chunk_markdown(body, corpus["chunk_max_chars"], corpus["chunk_overlap"]))
        chars_total += len(body)
    return {
        "chunks": chunks_total,
        "embed_requests": (chunks_total + settings.kb_embed_batch - 1) // settings.kb_embed_batch,
        "cost_estimate": round(chars_total / 1000 * settings.kb_embed_price_per_1k_tokens, 6),
    }
```

- [ ] **Step 4: 写 app/kb/worker.py**

```python
import os

from arq import cron
from arq.connections import RedisSettings

from kb import sync as sync_module
from kb.config import get_settings


def poll_minutes(interval: int) -> set[int]:
    return set(range(0, 60, max(1, interval)))


async def run_sync_job(ctx, corpus_id: str, scope: str = "all",
                       file_path: str | None = None) -> str:
    return await sync_module.run_sync(get_settings(), corpus_id, scope, file_path)


async def rebuild_job(ctx, corpus_id: str, mode: str) -> str:
    return await sync_module.run_rebuild(get_settings(), corpus_id, mode)


async def poll_all(ctx) -> None:
    settings = get_settings()
    driver = sync_module.get_driver(settings)
    try:
        for corpus in sync_module.list_corpora(driver):
            if not corpus.get("archived"):
                await sync_module.run_sync(settings, corpus["corpus_id"])
    finally:
        driver.close()


class WorkerSettings:
    functions = [run_sync_job, rebuild_job, poll_all]
    cron_jobs = [
        cron(
            poll_all,
            minute=poll_minutes(int(os.environ.get("KB_POLL_INTERVAL_MINUTES", "30"))),
            run_at_startup=False,
        )
    ]
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://127.0.0.1:6380/0")
    )
    max_tries = 3
    job_timeout = 1800
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd app && set -a && . ../.env && set +a && .venv/Scripts/python -m pytest tests/test_sync.py -q
```

Expected: 4 passed。

- [ ] **Step 6: 启动 worker 并确认 cron 注册**

worker 容器内的嵌入调用需要密钥，启动前先在同一 shell 会话 export（见全局约束的密钥条款）：

```bash
docker compose up -d worker
sleep 5
docker logs kb-worker 2>&1 | grep -E "cron|Starting worker" | head -5
```

Expected: 日志含 `Starting worker for 3 functions: poll_all, rebuild_job, run_sync_job` 与 cron 计划行。

- [ ] **Step 7: 提交**

```bash
git add app/kb/sync.py app/kb/worker.py app/tests/test_sync.py
git commit -m "feat: add incremental sync pipeline with arq worker and 30-minute polling"
```

---

### Task 9: 检索编排

落实：FR-04、FR-05、FR-10，requirements-spec.md 第 6.4 节。

**Files:**
- Create: `app/kb/search.py`
- Create: `app/tests/test_search.py`

**Interfaces:**
- Consumes: `kb.embed.embed_texts`、`kb.qdrant_store.search_points / fetch_points / chunk_id`、`kb.neo4j_store.get_driver`。
- Produces:
  - `kb.search.rrf_fuse(ranked_lists: list[list[str]], k: int = 60, weights: list[float] | None = None) -> dict[str, float]`（weights 与 ranked_lists 等长，缺省全为 1.0）
  - `kb.search.read_context(corpus_root: str, payload: dict, max_chars: int = 2000) -> str | None`
  - `kb.search.expand_one_hop(driver, payloads: list[dict]) -> list[str]`（返回 chunk_id 列表）
  - `kb.search.class_matched_pairs(driver, corpus_id: str, payloads: list[dict], iris: set[str]) -> set[tuple[str, int]]`（本体类型过滤，iris 为子类闭包集合）
  - `async kb.search.run_search(settings, corpus_id: str, query: str, filters: dict | None = None, top_k: int = 10) -> list[dict]`（归档库返回空列表；图扩展开关与权重按库配置读取）
  - 结果元素字段：`chunk_id`、`content`、`context`、`anchor`、`score`、`vector_rank`、`fused_rank`、`heading_path`、`asset_rel_path`。

- [ ] **Step 1: 写失败测试 app/tests/test_search.py**

```python
from pathlib import Path

from kb.search import class_matched_pairs, read_context, rrf_fuse


def test_rrf_fuse_prefers_item_in_both_lists():
    scores = rrf_fuse([["a", "b", "c"], ["b", "d"]])
    assert max(scores, key=scores.get) == "b"
    assert scores["a"] > scores["c"]


def test_rrf_fuse_single_list_preserves_order():
    scores = rrf_fuse([["x", "y"]])
    assert scores["x"] > scores["y"]


def test_rrf_fuse_applies_list_weights():
    scores = rrf_fuse([["a"], ["a"]], weights=[1.0, 2.0])
    assert round(scores["a"], 6) == round(3.0 / 61, 6)


def test_class_matched_pairs_returns_matching_pairs():
    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def data(self):
            return self.rows

    class FakeSession:
        def run(self, query, **kwargs):
            return FakeResult([{"rel_path": "a.md", "seq": 0}])

    class FakeDriver:
        def session(self):
            return FakeSession()

    payloads = [{"asset_rel_path": "a.md", "seq": 0}]
    assert class_matched_pairs(FakeDriver(), "c1", payloads, {"Person", "Agent"}) == {("a.md", 0)}


def test_read_context_returns_heading_section(tmp_path: Path):
    note = tmp_path / "a.md"
    note.write_text("# 甲\n第一段\n\n## 乙\n第二段\n\n# 丙\n第三段", encoding="utf-8")
    payload = {"asset_rel_path": "a.md", "heading_path": ["甲", "乙"], "seq": 1}
    context = read_context(str(tmp_path), payload)
    assert context == "第二段"


def test_read_context_missing_file_returns_none(tmp_path: Path):
    assert read_context(str(tmp_path), {"asset_rel_path": "nope.md", "heading_path": []}) is None


def test_read_context_without_heading_returns_head(tmp_path: Path):
    note = tmp_path / "b.md"
    note.write_text("纯文本正文", encoding="utf-8")
    assert read_context(str(tmp_path), {"asset_rel_path": "b.md", "heading_path": []}) == "纯文本正文"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_search.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'kb.search'`。

- [ ] **Step 3: 写 app/kb/search.py**

```python
import re
from pathlib import Path

from qdrant_client import QdrantClient

from kb.config import Settings
from kb.embed import embed_texts
from kb.neo4j_store import get_corpus, get_driver, get_ontology
from kb.ontology import subclass_closure
from kb.qdrant_store import chunk_id, fetch_points, search_points

EXPAND_QUERY = """
UNWIND $pairs AS pair
MATCH (e:Entity)
WHERE any(a IN e.anchors WHERE a.rel_path = pair.rel_path AND a.seq = pair.seq)
WITH collect(DISTINCT e) AS seeds
UNWIND seeds AS seed
MATCH (seed)-[r:REL {state: 'confirmed'}]-(other:Entity)
UNWIND other.anchors AS a
RETURN DISTINCT a.rel_path AS rel_path, a.seq AS seq, a.sha256 AS sha256
"""

CLASS_MATCH_QUERY = """
UNWIND $pairs AS pair
MATCH (e:Entity {corpus_id: $corpus_id})-[:INSTANCE_OF]->(c:OntClass)
WHERE c.iri IN $iris
  AND any(a IN e.anchors WHERE a.rel_path = pair.rel_path AND a.seq = pair.seq)
RETURN DISTINCT pair.rel_path AS rel_path, pair.seq AS seq
"""


def rrf_fuse(ranked_lists: list[list[str]], k: int = 60,
             weights: list[float] | None = None) -> dict[str, float]:
    weights = weights or [1.0] * len(ranked_lists)
    scores: dict[str, float] = {}
    for ranked, weight in zip(ranked_lists, weights):
        for rank, item in enumerate(ranked):
            scores[item] = scores.get(item, 0.0) + weight / (k + rank + 1)
    return scores


def class_matched_pairs(driver, corpus_id: str, payloads: list[dict],
                        iris: set[str]) -> set[tuple[str, int]]:
    pairs = [
        {"rel_path": p["asset_rel_path"], "seq": p["seq"]}
        for p in payloads
        if p.get("asset_rel_path") is not None
    ]
    if not pairs or not iris:
        return set()
    with driver.session() as session:
        rows = session.run(
            CLASS_MATCH_QUERY, corpus_id=corpus_id, pairs=pairs, iris=list(iris)
        ).data()
    return {(row["rel_path"], row["seq"]) for row in rows}


def read_context(corpus_root: str, payload: dict, max_chars: int = 2000) -> str | None:
    path = Path(corpus_root) / payload["asset_rel_path"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    heading_path = payload.get("heading_path") or []
    if not heading_path:
        return text[:max_chars]
    title = heading_path[-1]
    match = re.search(rf"^(#{{1,6}})\s+{re.escape(title)}\s*$", text, re.MULTILINE)
    if not match:
        return text[:max_chars]
    level = len(match.group(1))
    remainder = text[match.end():]
    nxt = re.search(rf"^#{{1,{level}}}\s+", remainder, re.MULTILINE)
    section = remainder[:nxt.start()] if nxt else remainder
    return section.strip()[:max_chars] or None


def expand_one_hop(driver, payloads: list[dict]) -> list[str]:
    pairs = [
        {"rel_path": p["asset_rel_path"], "seq": p["seq"]}
        for p in payloads
        if p.get("asset_rel_path") is not None
    ]
    if not pairs:
        return []
    with driver.session() as session:
        rows = session.run(EXPAND_QUERY, pairs=pairs).data()
    ids = []
    for row in rows:
        if row["sha256"]:
            ids.append(chunk_id(row["rel_path"], row["sha256"]))
    return ids


async def run_search(settings: Settings, corpus_id: str, query: str,
                     filters: dict | None = None, top_k: int = 10) -> list[dict]:
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    driver = get_driver(settings)
    try:
        corpus = get_corpus(driver, corpus_id)
        if corpus is None or corpus.get("archived"):
            return []
        vectors, _ = await embed_texts(settings, [query])
        hits = search_points(client, corpus_id, vectors[0], filters or {}, top_k=top_k)
        class_iri = (filters or {}).get("class_iri")
        if class_iri:
            ontology = get_ontology(driver, corpus_id)
            iris = subclass_closure(ontology["classes"]).get(class_iri, {class_iri})
            matched = class_matched_pairs(
                driver, corpus_id, [hit.payload for hit in hits], iris
            )
            hits = [
                hit
                for hit in hits
                if (hit.payload["asset_rel_path"], hit.payload["seq"]) in matched
            ]
        vector_ranked = [hit.id for hit in hits]
        by_id = {hit.id: hit for hit in hits}
        graph_ranked: list[str] = []
        if corpus.get("graph_expand_enabled", True):
            graph_ranked = expand_one_hop(driver, [hit.payload for hit in hits])
            missing = [pid for pid in graph_ranked if pid not in by_id]
            for point in fetch_points(client, corpus_id, missing):
                by_id[point.id] = point
        graph_weight = float(corpus.get("graph_weight", 1.0))
        fused = rrf_fuse([vector_ranked, graph_ranked], k=60, weights=[1.0, graph_weight])
        ordered = [pid for pid, _ in sorted(fused.items(), key=lambda kv: -kv[1])][:top_k]
        vector_rank = {pid: rank + 1 for rank, pid in enumerate(vector_ranked)}
        results = []
        for fused_rank, pid in enumerate(ordered, start=1):
            point = by_id.get(pid)
            if point is None:
                continue
            payload = point.payload
            context = read_context(settings.kb_corpus_root, payload)
            if context is None:
                continue
            results.append(
                {
                    "chunk_id": pid,
                    "content": payload.get("text", "")[:300],
                    "context": context,
                    "anchor": {
                        "rel_path": payload["asset_rel_path"],
                        "seq": payload["seq"],
                        "sha256": payload["chunk_sha256"],
                    },
                    "score": round(fused[pid], 6),
                    "vector_rank": vector_rank.get(pid),
                    "fused_rank": fused_rank,
                    "heading_path": payload.get("heading_path", []),
                    "asset_rel_path": payload["asset_rel_path"],
                }
            )
        return results
    finally:
        driver.close()
        client.close()
```

`read_context` 返回 None 表示锚点已失效（文件被删或移动），该结果按 requirements-spec.md 第 6.4 节第 5 步丢弃并应在调用侧记入任务日志。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd app && .venv/Scripts/python -m pytest tests/test_search.py -q
```

Expected: 7 passed。

- [ ] **Step 5: 提交**

```bash
git add app/kb/search.py app/tests/test_search.py
git commit -m "feat: add hybrid retrieval with rrf fusion and graph one-hop expansion"
```

---

### Task 10: REST 接口层

落实：FR-01 至 FR-11、FR-13 的接口面，requirements-spec.md 第 4.1 节，NFR-06。

**Files:**
- Create: `app/kb/deps.py`、`app/kb/schemas.py`、`app/kb/graph_view.py`
- Create: `app/kb/routers/corpora.py`、`tasks.py`、`search.py`、`ontology.py`、`entities.py`、`graph.py`、`stats.py`
- Modify: `app/kb/main.py`
- Create: `app/tests/test_api.py`

**Interfaces:**
- Consumes: Task 5 至 Task 9 的全部 store 与算法模块。
- Produces:
  - `kb.deps.get_neo4j()` 与 `kb.deps.get_qdrant_client()`（FastAPI 依赖，负责关闭连接）。
  - `kb.schemas` 中的请求模型（字段与 requirements-spec.md 第 4.1 节一致）。
  - `kb.main.create_app()` 挂载七个 router 与 arq 连接池（`app.state.arq`）。
  - 响应统一为 `{"data": ...}`；应用业务错误统一为 `{"error": {"code": "...", "message": "..."}}`，HTTP 400 用于业务校验失败、401 用于令牌错误、404 用于资源不存在；422 请求校验错误保留 FastAPI 默认结构。

- [ ] **Step 1: 写 app/kb/deps.py**

```python
from qdrant_client import QdrantClient

from kb.config import get_settings
from kb.neo4j_store import get_driver


def get_neo4j():
    driver = get_driver(get_settings())
    try:
        yield driver
    finally:
        driver.close()


def get_qdrant_client():
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
    try:
        yield client
    finally:
        client.close()
```

- [ ] **Step 2: 写 app/kb/schemas.py**

```python
from pydantic import BaseModel, Field


class CorpusCreate(BaseModel):
    name: str
    subdir: str
    ontology_prefix: str
    embedding_model: str = "text-embedding-v4"
    vector_dim: int = 1024
    chunk_max_chars: int = 700
    chunk_overlap: int = 60
    graph_expand_enabled: bool = True
    graph_weight: float = 1.0


class CorpusUpdate(BaseModel):
    name: str | None = None
    chunk_max_chars: int | None = None
    chunk_overlap: int | None = None
    graph_expand_enabled: bool | None = None
    graph_weight: float | None = None
    archived: bool | None = None


class SyncTrigger(BaseModel):
    scope: str = "all"
    file_path: str | None = None


class RebuildTrigger(BaseModel):
    mode: str


class SearchFilters(BaseModel):
    tags: list[str] = Field(default_factory=list)
    time_from: float | None = None
    time_to: float | None = None
    class_iri: str | None = None


class SearchRequest(BaseModel):
    corpus_id: str
    query: str
    top_k: int = 10
    filters: SearchFilters = Field(default_factory=SearchFilters)


class OntClassIn(BaseModel):
    iri: str
    prefix_local: str
    label_zh: str
    definition: str
    parent_iris: list[str] = Field(default_factory=list)
    disjoint_with: list[str] = Field(default_factory=list)
    equivalent_to: str | None = None
    aliases: list[str] = Field(default_factory=list)
    min_cardinality: int | None = None
    max_cardinality: int | None = None


class OntObjPropIn(BaseModel):
    iri: str
    prefix_local: str
    label_zh: str
    definition: str
    domain_iri: str
    range_iri: str
    characteristics: list[str] = Field(default_factory=list)
    min_cardinality: int | None = None
    max_cardinality: int | None = None


class OntDataPropIn(BaseModel):
    iri: str
    prefix_local: str
    label_zh: str
    definition: str
    domain_iri: str
    xsd_range: str = "http://www.w3.org/2001/XMLSchema#string"


class EntityIn(BaseModel):
    label: str
    class_iri: str
    aliases: list[str] = Field(default_factory=list)
    anchor: dict


class EntitiesMerge(BaseModel):
    keep: str
    drop: str


class EntitiesSplit(BaseModel):
    eid: str
    new_label: str
    class_iri: str | None = None
    anchors: list[dict]


class RelationIn(BaseModel):
    from_eid: str
    to_eid: str
    type_iri: str
    evidence_anchors: list[dict] = Field(default_factory=list)


class PendingResolve(BaseModel):
    action: str
    new_class_iri: str | None = None
```

- [ ] **Step 3: 写 app/kb/routers/corpora.py**

```python
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from kb.auth import require_token
from kb.config import get_settings
from kb.deps import get_neo4j, get_qdrant_client
from kb.neo4j_store import (
    delete_corpus,
    get_corpus,
    get_ontology,
    init_schema,
    list_corpora,
    new_ont_version,
    upsert_corpus,
)
from kb.ontology import export_ttl
from kb.qdrant_store import collection_name, ensure_collection
from kb.schemas import CorpusCreate, CorpusUpdate, RebuildTrigger
from kb.sync import estimate_rebuild

router = APIRouter(prefix="/api/v1/corpora", dependencies=[Depends(require_token)])


@router.post("")
async def create_corpus(body: CorpusCreate, driver=Depends(get_neo4j), client=Depends(get_qdrant_client)):
    settings = get_settings()
    corpus_dir = Path(settings.kb_corpus_root) / body.subdir
    if not corpus_dir.is_dir():
        raise HTTPException(400, detail={"code": "SUBDIR_NOT_FOUND", "message": f"权威源子目录不存在: {body.subdir}"})
    init_schema(driver)
    corpus_id = uuid4().hex[:12]
    ensure_collection(client, corpus_id, body.vector_dim)
    corpus = {**body.model_dump(), "corpus_id": corpus_id, "archived": False, "created_at": time.time()}
    upsert_corpus(driver, corpus)
    new_ont_version(driver, corpus_id)
    export_ttl(get_ontology(driver, corpus_id), f"{settings.kb_ontology_export_dir}/{corpus_id}.ttl")
    return {"data": corpus}


@router.get("")
async def read_corpora(driver=Depends(get_neo4j)):
    return {"data": list_corpora(driver)}


@router.get("/{corpus_id}")
async def read_corpus(corpus_id: str, driver=Depends(get_neo4j), client=Depends(get_qdrant_client)):
    corpus = get_corpus(driver, corpus_id)
    if corpus is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    name = collection_name(corpus_id)
    points = client.count(collection_name=name).count if client.collection_exists(name) else 0
    return {"data": {**corpus, "points": points}}


@router.patch("/{corpus_id}")
async def patch_corpus(corpus_id: str, body: CorpusUpdate, driver=Depends(get_neo4j)):
    corpus = get_corpus(driver, corpus_id)
    if corpus is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    changes = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not changes:
        return {"data": corpus}
    upsert_corpus(driver, {**corpus, **changes})
    return {"data": get_corpus(driver, corpus_id)}


@router.delete("/{corpus_id}")
async def remove_corpus(corpus_id: str, driver=Depends(get_neo4j), client=Depends(get_qdrant_client)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    name = collection_name(corpus_id)
    if client.collection_exists(name):
        client.delete_collection(name)
    delete_corpus(driver, corpus_id)
    return {"data": {"deleted": corpus_id}}


@router.post("/{corpus_id}/sync")
async def trigger_sync(corpus_id: str, request: Request, body: SyncTrigger | None = None, driver=Depends(get_neo4j)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    trigger = body or SyncTrigger()
    job = await request.app.state.arq.enqueue_job(
        "run_sync_job", corpus_id, trigger.scope, trigger.file_path
    )
    if job is None:
        raise HTTPException(409, detail={"code": "JOB_BUSY", "message": "同名任务已在队列中"})
    return {"data": {"task_id": job.job_id}}


@router.get("/{corpus_id}/rebuild/estimate")
async def rebuild_estimate(corpus_id: str, driver=Depends(get_neo4j)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    return {"data": await estimate_rebuild(get_settings(), corpus_id)}


@router.post("/{corpus_id}/rebuild")
async def trigger_rebuild(corpus_id: str, request: Request, body: RebuildTrigger, driver=Depends(get_neo4j)):
    if get_corpus(driver, corpus_id) is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    if body.mode not in ("structure", "reembed"):
        raise HTTPException(400, detail={"code": "BAD_REBUILD_MODE", "message": body.mode})
    job = await request.app.state.arq.enqueue_job("rebuild_job", corpus_id, body.mode)
    if job is None:
        raise HTTPException(409, detail={"code": "JOB_BUSY", "message": "同名任务已在队列中"})
    return {"data": {"task_id": job.job_id}}


@router.get("/{corpus_id}/assets")
async def list_assets(corpus_id: str, driver=Depends(get_neo4j), client=Depends(get_qdrant_client)):
    from kb.qdrant_store import get_asset_hashes
    from kb.sync import scan_assets

    corpus = get_corpus(driver, corpus_id)
    if corpus is None:
        raise HTTPException(404, detail={"code": "CORPUS_NOT_FOUND", "message": corpus_id})
    root = Path(get_settings().kb_corpus_root) / corpus["subdir"]
    assets = scan_assets(root) if root.is_dir() else []
    hashes = get_asset_hashes(client, corpus_id, [a["rel_path"] for a in assets])
    for asset in assets:
        asset["synced"] = hashes.get(asset["rel_path"]) == asset["sha256"]
    return {"data": assets}


@router.get("/{corpus_id}/assets/{rel_path:path}/chunks")
async def list_chunks(corpus_id: str, rel_path: str, client=Depends(get_qdrant_client)):
    name = collection_name(corpus_id)
    if not client.collection_exists(name):
        raise HTTPException(404, detail={"code": "COLLECTION_NOT_FOUND", "message": name})
    points, _ = client.scroll(
        collection_name=name,
        scroll_filter=Filter(
            must=[FieldCondition(key="asset_rel_path", match=MatchValue(value=rel_path))]
        ),
        limit=1000,
        with_payload=True,
        with_vectors=False,
    )
    chunks = sorted(
        (
            {
                "chunk_id": point.id,
                "seq": point.payload["seq"],
                "heading_path": point.payload["heading_path"],
                "char_len": point.payload["char_len"],
                "chunk_sha256": point.payload["chunk_sha256"],
                "text": point.payload["text"],
            }
            for point in points
        ),
        key=lambda chunk: chunk["seq"],
    )
    return {"data": chunks}
```

corpora.py 的 imports 中加入：

```python
from qdrant_client.models import FieldCondition, Filter, MatchValue
```

- [ ] **Step 4: 写 app/kb/routers/tasks.py 与 search.py**

`tasks.py`：

```python
from fastapi import APIRouter, Depends, HTTPException

from kb.auth import require_token
from kb.deps import get_neo4j
from kb.neo4j_store import get_task

router = APIRouter(prefix="/api/v1/tasks", dependencies=[Depends(require_token)])


@router.get("/{task_id}")
async def read_task(task_id: str, driver=Depends(get_neo4j)):
    task = get_task(driver, task_id)
    if task is None:
        raise HTTPException(404, detail={"code": "TASK_NOT_FOUND", "message": task_id})
    return {"data": task}
```

`search.py`：

```python
from fastapi import APIRouter, Depends

from kb.auth import require_token
from kb.config import get_settings
from kb.schemas import SearchRequest
from kb.search import run_search

router = APIRouter(prefix="/api/v1/search", dependencies=[Depends(require_token)])


@router.post("")
async def search(body: SearchRequest):
    results = await run_search(
        get_settings(),
        body.corpus_id,
        body.query,
        body.filters.model_dump(exclude_none=True),
        body.top_k,
    )
    return {"data": results}
```

- [ ] **Step 5: 写 app/kb/routers/ontology.py**

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from kb.auth import require_token
from kb.config import get_settings
from kb.deps import get_neo4j
from kb.neo4j_store import (
    delete_ont_class,
    delete_ont_data_prop,
    delete_ont_obj_prop,
    get_ontology,
    new_ont_version,
    write_ont_class,
    write_ont_data_prop,
    write_ont_obj_prop,
)
from kb.ontology import export_ttl, find_violations, validate_rl
from kb.proposals import create_pending
from kb.schemas import OntClassIn, OntDataPropIn, OntObjPropIn

router = APIRouter(prefix="/api/v1/ontology", dependencies=[Depends(require_token)])


def _reject(violations: list[str]) -> None:
    if violations:
        raise HTTPException(400, detail={"code": "OWL_RL_VIOLATION", "message": "; ".join(violations)})


def _save_and_export(driver, corpus_id: str, entry: dict, writer) -> dict:
    _reject(validate_rl(entry))
    writer(driver, corpus_id, entry)
    seq = new_ont_version(driver, corpus_id)
    ontology = get_ontology(driver, corpus_id)
    export_ttl(ontology, f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl")
    return {**entry, "ont_version": seq}


@router.get("/{corpus_id}")
async def read_ontology(corpus_id: str, driver=Depends(get_neo4j)):
    return {"data": get_ontology(driver, corpus_id)}


@router.post("/classes")
async def create_class(corpus_id: str, body: OntClassIn, driver=Depends(get_neo4j)):
    return {"data": _save_and_export(driver, corpus_id, body.model_dump(exclude_none=True), write_ont_class)}


@router.post("/object-properties")
async def create_obj_prop(corpus_id: str, body: OntObjPropIn, driver=Depends(get_neo4j)):
    entry = body.model_dump(exclude_none=True)
    saved = _save_and_export(driver, corpus_id, entry, write_ont_obj_prop)
    ontology = get_ontology(driver, corpus_id)
    violations = find_violations(driver, entry, ontology["classes"])
    return {"data": {**saved, "violations": violations}}


@router.post("/datatype-properties")
async def create_data_prop(corpus_id: str, body: OntDataPropIn, driver=Depends(get_neo4j)):
    return {"data": _save_and_export(driver, corpus_id, body.model_dump(exclude_none=True), write_ont_data_prop)}


@router.patch("/classes/{iri}")
async def patch_class(iri: str, corpus_id: str, body: OntClassIn, driver=Depends(get_neo4j)):
    entry = body.model_dump(exclude_none=True)
    entry["iri"] = iri
    return {"data": _save_and_export(driver, corpus_id, entry, write_ont_class)}


@router.delete("/classes/{iri}")
async def remove_class(iri: str, corpus_id: str, driver=Depends(get_neo4j)):
    affected = delete_ont_class(driver, corpus_id, iri)
    for row in affected:
        create_pending(
            driver,
            corpus_id,
            "violation",
            {
                "entity_eid": row["eid"],
                "entity_label": row["label"],
                "class_iri": iri,
                "reason": "class_deleted",
            },
        )
    seq = new_ont_version(driver, corpus_id)
    export_ttl(
        get_ontology(driver, corpus_id),
        f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl",
    )
    return {"data": {"deleted": iri, "affected_entities": len(affected), "ont_version": seq}}


@router.patch("/object-properties/{iri}")
async def patch_obj_prop(iri: str, corpus_id: str, body: OntObjPropIn, driver=Depends(get_neo4j)):
    entry = body.model_dump(exclude_none=True)
    entry["iri"] = iri
    saved = _save_and_export(driver, corpus_id, entry, write_ont_obj_prop)
    violations = find_violations(driver, entry, get_ontology(driver, corpus_id)["classes"])
    return {"data": {**saved, "violations": violations}}


@router.delete("/object-properties/{iri}")
async def remove_obj_prop(iri: str, corpus_id: str, driver=Depends(get_neo4j)):
    affected = delete_ont_obj_prop(driver, corpus_id, iri)
    for row in affected:
        create_pending(
            driver,
            corpus_id,
            "violation",
            {
                "from_eid": row["from_eid"],
                "to_eid": row["to_eid"],
                "type_iri": iri,
                "reason": "property_deleted",
            },
        )
    seq = new_ont_version(driver, corpus_id)
    export_ttl(
        get_ontology(driver, corpus_id),
        f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl",
    )
    return {"data": {"deleted": iri, "affected_relations": len(affected), "ont_version": seq}}


@router.patch("/datatype-properties/{iri}")
async def patch_data_prop(iri: str, corpus_id: str, body: OntDataPropIn, driver=Depends(get_neo4j)):
    entry = body.model_dump(exclude_none=True)
    entry["iri"] = iri
    return {"data": _save_and_export(driver, corpus_id, entry, write_ont_data_prop)}


@router.delete("/datatype-properties/{iri}")
async def remove_data_prop(iri: str, corpus_id: str, driver=Depends(get_neo4j)):
    delete_ont_data_prop(driver, corpus_id, iri)
    seq = new_ont_version(driver, corpus_id)
    export_ttl(
        get_ontology(driver, corpus_id),
        f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl",
    )
    return {"data": {"deleted": iri, "ont_version": seq}}


@router.get("/export/{corpus_id}")
async def download_ttl(corpus_id: str):
    path = f"{get_settings().kb_ontology_export_dir}/{corpus_id}.ttl"
    return FileResponse(path, media_type="text/turtle", filename=f"{corpus_id}.ttl")
```

- [ ] **Step 6: 写 app/kb/routers/entities.py、graph.py、stats.py**

`entities.py`：

```python
from fastapi import APIRouter, Depends, HTTPException

from kb.auth import require_token
from kb.deps import get_neo4j
from kb.neo4j_store import get_ontology
from kb.ontology import check_relation_valid
from kb.proposals import (
    create_pending,
    ensure_entity,
    list_pending,
    resolve_pending,
    split_entity,
)
from kb.schemas import EntitiesMerge, EntitiesSplit, EntityIn, PendingResolve, RelationIn

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])

MERGE_QUERY = """
MATCH (keep:Entity {eid: $keep}), (drop:Entity {eid: $drop})
WITH keep, drop, [a IN drop.anchors WHERE NOT a IN keep.anchors] AS extra
SET keep.anchors = keep.anchors + extra,
    keep.aliases = keep.aliases + [a IN drop.aliases WHERE NOT a IN keep.aliases]
WITH keep, drop
MATCH (drop)-[r:REL]->(other:Entity) WHERE other <> keep
CREATE (keep)-[nr:REL]->(other) SET nr = properties(r)
WITH keep, drop
MATCH (other:Entity)-[r:REL]->(drop) WHERE other <> keep
CREATE (other)-[nr:REL]->(keep) SET nr = properties(r)
DETACH DELETE drop
RETURN keep.eid AS eid, size(keep.anchors) AS anchors
"""


@router.get("/entities")
async def read_entities(corpus_id: str, driver=Depends(get_neo4j)):
    rows = driver.session().run(
        "MATCH (e:Entity {corpus_id: $id}) RETURN e", id=corpus_id
    ).data()
    return {"data": [dict(r["e"]) for r in rows]}


@router.post("/entities")
async def create_entity(corpus_id: str, body: EntityIn, driver=Depends(get_neo4j)):
    eid = ensure_entity(driver, corpus_id, body.label, body.class_iri, body.anchor, ont_version=0)
    return {"data": {"eid": eid}}


@router.post("/entities/merge")
async def merge_entities(body: EntitiesMerge, driver=Depends(get_neo4j)):
    row = driver.session().run(MERGE_QUERY, keep=body.keep, drop=body.drop).single()
    if row is None:
        raise HTTPException(404, detail={"code": "ENTITY_NOT_FOUND", "message": body.keep})
    return {"data": {"eid": row["eid"], "anchors": row["anchors"]}}


@router.post("/entities/split")
async def split_entity_route(body: EntitiesSplit, driver=Depends(get_neo4j)):
    try:
        result = split_entity(driver, body.eid, body.new_label, body.anchors, body.class_iri)
    except KeyError:
        raise HTTPException(404, detail={"code": "ENTITY_NOT_FOUND", "message": body.eid})
    except ValueError as exc:
        raise HTTPException(400, detail={"code": "SPLIT_INVALID", "message": str(exc)})
    return {"data": result}


@router.post("/relations")
async def create_relation(body: RelationIn, driver=Depends(get_neo4j)):
    with driver.session() as session:
        a = session.run("MATCH (e:Entity {eid: $eid}) RETURN e", eid=body.from_eid).single()
        b = session.run("MATCH (e:Entity {eid: $eid}) RETURN e", eid=body.to_eid).single()
    if a is None or b is None:
        raise HTTPException(404, detail={"code": "ENTITY_NOT_FOUND", "message": body.from_eid})
    from_node, to_node = dict(a["e"]), dict(b["e"])
    if from_node.get("corpus_id") != to_node.get("corpus_id"):
        raise HTTPException(
            400, detail={"code": "CROSS_CORPUS_RELATION", "message": "关系两端实体必须属于同一库"}
        )
    corpus_id = from_node["corpus_id"]
    ontology = get_ontology(driver, corpus_id)
    obj_prop = next(
        (p for p in ontology["object_properties"] if p["iri"] == body.type_iri), None
    )
    if obj_prop is None:
        raise HTTPException(400, detail={"code": "PROPERTY_NOT_FOUND", "message": body.type_iri})
    reasons = check_relation_valid(
        ontology["classes"], obj_prop, from_node["class_iri"], to_node["class_iri"]
    )
    if reasons:
        pid = create_pending(
            driver,
            corpus_id,
            "violation",
            {
                "from_eid": body.from_eid,
                "to_eid": body.to_eid,
                "type_iri": body.type_iri,
                "reason": ",".join(reasons),
            },
        )
        return {"data": {"created": False, "pending_pid": pid, "violations": reasons}}
    driver.session().run(
        """
        MATCH (a:Entity {eid: $from_eid}), (b:Entity {eid: $to_eid})
        CREATE (a)-[r:REL {type_iri: $type_iri, evidence_anchors: $anchors, state: 'confirmed'}]->(b)
        """,
        from_eid=body.from_eid, to_eid=body.to_eid, type_iri=body.type_iri,
        anchors=body.evidence_anchors,
    )
    return {"data": {"created": True}}


@router.get("/pending")
async def read_pending(corpus_id: str | None = None, driver=Depends(get_neo4j)):
    return {"data": list_pending(driver, corpus_id)}


@router.post("/pending/{pid}/resolve")
async def resolve(pid: str, body: PendingResolve, driver=Depends(get_neo4j)):
    if body.action not in {"confirm", "reject", "retype"}:
        raise HTTPException(400, detail={"code": "BAD_ACTION", "message": body.action})
    return {"data": resolve_pending(driver, pid, body.action, body.new_class_iri)}
```

`app/kb/graph_view.py`：

```python
GRAPH_QUERY_TEMPLATE = """
MATCH path = (center:Entity {{eid: $eid}})-[:REL*1..{depth}]-(other:Entity)
RETURN [n IN nodes(path) | {{eid: n.eid, label: n.label, class_iri: n.class_iri,
                            anchors: size(n.anchors)}}] AS nodes,
       [r IN relationships(path) | {{type_iri: r.type_iri, state: r.state,
                                    from: startNode(r).eid, to: endNode(r).eid}}] AS edges
"""


def clamp_depth(depth: int) -> int:
    return min(max(depth, 1), 2)


def read_graph_data(driver, entity_id: str, depth: int = 2) -> dict:
    rows = driver.session().run(
        GRAPH_QUERY_TEMPLATE.format(depth=clamp_depth(depth)), eid=entity_id
    ).data()
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for row in rows:
        for node in row["nodes"]:
            nodes[node["eid"]] = node
        edges.extend(row["edges"])
    return {"nodes": list(nodes.values()), "edges": edges}
```

`graph.py`：

```python
from fastapi import APIRouter, Depends

from kb.auth import require_token
from kb.deps import get_neo4j
from kb.graph_view import read_graph_data

router = APIRouter(prefix="/api/v1/graph", dependencies=[Depends(require_token)])


@router.get("")
async def read_graph(entity_id: str, depth: int = 2, driver=Depends(get_neo4j)):
    return {"data": read_graph_data(driver, entity_id, depth)}
```

`stats.py`：

```python
from fastapi import APIRouter, Depends

from kb.auth import require_token
from kb.deps import get_neo4j

router = APIRouter(prefix="/api/v1/stats", dependencies=[Depends(require_token)])


@router.get("/corpus/{corpus_id}")
async def corpus_stats(corpus_id: str, driver=Depends(get_neo4j)):
    row = driver.session().run(
        """
        MATCH (t:OpsTask {corpus_id: $id})
        OPTIONAL MATCH (p:PendingItem {corpus_id: $id, status: 'open'})
        RETURN count(t) AS tasks,
               sum(t.tokens) AS tokens,
               sum(t.embed_retries) AS retries,
               sum(t.cost_estimate) AS cost,
               sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
               count(DISTINCT p) AS pending
        """,
        id=corpus_id,
    ).single()
    return {"data": dict(row)}
```

- [ ] **Step 7: 改写 app/kb/main.py 挂载路由与队列**

```python
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.exceptions import HTTPException as HttpError
from fastapi.responses import JSONResponse

from kb.config import get_settings
from kb.routers import corpora, entities, graph, ontology, search, stats, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.arq = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    yield
    await app.state.arq.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="center-kb", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(HttpError)
    async def http_error_handler(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    for module in (corpora, tasks, search, ontology, entities, graph, stats):
        app.include_router(module.router)
    return app


app = create_app()
```

业务错误经异常处理器统一为 `{"error": {"code": ..., "message": ...}}`；请求校验错误（422）保留 FastAPI 默认结构。

- [ ] **Step 8: 写 app/tests/test_api.py**

```python
import pytest
from fastapi.testclient import TestClient

from kb.config import get_settings
from kb.main import create_app

HEADERS = {"Authorization": "Bearer test-token"}


@pytest.fixture
def host_env(tmp_path, monkeypatch):
    (tmp_path / "acc").mkdir()
    (tmp_path / "ontology").mkdir()
    monkeypatch.setenv("KB_CORPUS_ROOT", str(tmp_path))
    monkeypatch.setenv("KB_ONTOLOGY_EXPORT_DIR", str(tmp_path / "ontology"))
    monkeypatch.setenv("KB_AUTH_TOKEN", "test-token")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.mark.integration
def test_corpus_lifecycle(host_env):
    client = TestClient(create_app())
    created = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": "验收库", "subdir": "acc", "ontology_prefix": "acc", "vector_dim": 4,
    })
    assert created.status_code == 200
    corpus_id = created.json()["data"]["corpus_id"]
    assert (host_env / "ontology" / f"{corpus_id}.ttl").exists()

    assert corpus_id in [c["corpus_id"] for c in client.get("/api/v1/corpora", headers=HEADERS).json()["data"]]

    detail = client.get(f"/api/v1/corpora/{corpus_id}", headers=HEADERS)
    assert detail.json()["data"]["points"] == 0

    assert client.delete(f"/api/v1/corpora/{corpus_id}", headers=HEADERS).status_code == 200
    assert client.get(f"/api/v1/corpora/{corpus_id}", headers=HEADERS).status_code == 404


@pytest.mark.integration
def test_create_corpus_rejects_missing_subdir(host_env):
    client = TestClient(create_app())
    resp = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": "坏库", "subdir": "不存在", "ontology_prefix": "bad", "vector_dim": 4,
    })
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SUBDIR_NOT_FOUND"


@pytest.mark.integration
def test_ontology_rejects_relative_iri(host_env):
    client = TestClient(create_app())
    corpus_id = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": "本体库", "subdir": "acc", "ontology_prefix": "ont", "vector_dim": 4,
    }).json()["data"]["corpus_id"]

    bad = client.post(
        f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS,
        json={"iri": "Project", "prefix_local": "Project", "label_zh": "项目", "definition": "交付单元"},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "OWL_RL_VIOLATION"

    good = client.post(
        f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS,
        json={"iri": "http://kb.local/o/ont#Project", "prefix_local": "Project",
              "label_zh": "项目", "definition": "交付单元", "aliases": ["项目组"]},
    )
    assert good.status_code == 200
    exported = client.get(f"/api/v1/ontology/export/{corpus_id}", headers=HEADERS)
    assert "Project" in exported.text


@pytest.mark.integration
def test_entity_split_moves_anchors(host_env):
    client = TestClient(create_app())
    corpus_id = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": "拆分库", "subdir": "acc", "ontology_prefix": "spl", "vector_dim": 4,
    }).json()["data"]["corpus_id"]
    client.post(f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS, json={
        "iri": "http://kb.local/o/spl#Project", "prefix_local": "Project",
        "label_zh": "项目", "definition": "交付单元",
    })
    anchor_a = {"rel_path": "acc/a.md", "seq": 0, "sha256": "sa"}
    anchor_b = {"rel_path": "acc/b.md", "seq": 0, "sha256": "sb"}
    for anchor in (anchor_a, anchor_b):
        resp = client.post(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS, json={
            "label": "项目组", "class_iri": "http://kb.local/o/spl#Project", "anchor": anchor,
        })
        assert resp.status_code == 200
    entities = client.get(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS).json()["data"]
    assert len(entities) == 1
    assert len(entities[0]["anchors"]) == 2

    split = client.post("/api/v1/entities/split", headers=HEADERS, json={
        "eid": entities[0]["eid"], "new_label": "项目组-子", "anchors": [anchor_a],
    })
    assert split.status_code == 200
    body = split.json()["data"]
    assert body["src_anchors"] == 1 and body["new_anchors"] == 1
    after = client.get(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS).json()["data"]
    assert sum(len(e["anchors"]) for e in after) == 2


@pytest.mark.integration
def test_ontology_delete_enqueues_violations(host_env):
    client = TestClient(create_app())
    corpus_id = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": "删除库", "subdir": "acc", "ontology_prefix": "del", "vector_dim": 4,
    }).json()["data"]["corpus_id"]
    client.post(f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS, json={
        "iri": "http://kb.local/o/del#Project", "prefix_local": "Project",
        "label_zh": "项目", "definition": "交付单元",
    })
    client.post(f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS, json={
        "iri": "http://kb.local/o/del#Person", "prefix_local": "Person",
        "label_zh": "人员", "definition": "个体",
    })
    client.post(f"/api/v1/ontology/object-properties?corpus_id={corpus_id}", headers=HEADERS, json={
        "iri": "http://kb.local/o/del#memberOf", "prefix_local": "memberOf",
        "label_zh": "属于", "definition": "人员属于项目",
        "domain_iri": "http://kb.local/o/del#Person",
        "range_iri": "http://kb.local/o/del#Project",
    })
    person = client.post(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS, json={
        "label": "人员甲", "class_iri": "http://kb.local/o/del#Person",
        "anchor": {"rel_path": "acc/a.md", "seq": 0, "sha256": "sa"},
    }).json()["data"]["eid"]
    project = client.post(f"/api/v1/entities?corpus_id={corpus_id}", headers=HEADERS, json={
        "label": "项目乙", "class_iri": "http://kb.local/o/del#Project",
        "anchor": {"rel_path": "acc/b.md", "seq": 0, "sha256": "sb"},
    }).json()["data"]["eid"]
    rel = client.post("/api/v1/relations", headers=HEADERS, json={
        "from_eid": person, "to_eid": project,
        "type_iri": "http://kb.local/o/del#memberOf",
    })
    assert rel.status_code == 200 and rel.json()["data"]["created"] is True

    deleted_prop = client.delete(
        f"/api/v1/ontology/object-properties/http%3A%2F%2Fkb.local%2Fo%2Fdel%23memberOf?corpus_id={corpus_id}",
        headers=HEADERS,
    )
    assert deleted_prop.status_code == 200
    assert deleted_prop.json()["data"]["affected_relations"] == 1

    deleted_class = client.delete(
        f"/api/v1/ontology/classes/http%3A%2F%2Fkb.local%2Fo%2Fdel%23Project?corpus_id={corpus_id}",
        headers=HEADERS,
    )
    assert deleted_class.status_code == 200
    assert deleted_class.json()["data"]["affected_entities"] == 1

    pending = client.get(f"/api/v1/pending?corpus_id={corpus_id}", headers=HEADERS).json()["data"]
    reasons = [p["payload"].get("reason") for p in pending]
    assert "property_deleted" in reasons
    assert "class_deleted" in reasons


@pytest.mark.integration
def test_ontology_patch_class_updates_ttl(host_env):
    client = TestClient(create_app())
    corpus_id = client.post("/api/v1/corpora", headers=HEADERS, json={
        "name": "改库", "subdir": "acc", "ontology_prefix": "pat", "vector_dim": 4,
    }).json()["data"]["corpus_id"]
    payload = {
        "iri": "http://kb.local/o/pat#Project", "prefix_local": "Project",
        "label_zh": "项目", "definition": "原始定义",
    }
    assert client.post(
        f"/api/v1/ontology/classes?corpus_id={corpus_id}", headers=HEADERS, json=payload
    ).status_code == 200
    patched = client.patch(
        f"/api/v1/ontology/classes/http%3A%2F%2Fkb.local%2Fo%2Fpat%23Project?corpus_id={corpus_id}",
        headers=HEADERS,
        json={**payload, "definition": "修订后的定义"},
    )
    assert patched.status_code == 200
    ttl = (host_env / "ontology" / f"{corpus_id}.ttl").read_text(encoding="utf-8")
    assert "修订后的定义" in ttl


def test_token_required(host_env):
    assert TestClient(create_app()).get("/api/v1/corpora").status_code == 401
```

- [ ] **Step 9: 运行全部测试**

```bash
cd app && set -a && . ../.env && set +a && KB_AUTH_TOKEN=test-token REDIS_URL="redis://:${REDIS_PASSWORD}@127.0.0.1:6380/0" NEO4J_URI=bolt://127.0.0.1:7687 .venv/Scripts/python -m pytest -q
```

Expected: 全部通过，无 skip 之外的失败。

- [ ] **Step 10: 容器内端到端验证**

```bash
docker compose up -d --build api worker
TOKEN=$(grep '^KB_AUTH_TOKEN=' .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8101/api/v1/corpora
curl -s http://127.0.0.1:8101/api/v1/corpora | head -c 120
```

Expected: 第一条返回 `{"data":[]}`；第二条返回 401 且不含令牌。

- [ ] **Step 11: 提交**

```bash
git add app/kb app/tests/test_api.py
git commit -m "feat: add rest api layer for corpora ontology entities search and stats"
```

---

### Task 11: Web 管理界面

落实：FR-01 至 FR-11 的界面面，NFR-06、NFR-07。

**Files:**
- Create: `web/package.json`、`web/vite.config.js`、`web/index.html`、`web/Dockerfile`、`web/nginx.conf`
- Create: `web/src/main.js`、`web/src/App.vue`、`web/src/api.js`、`web/src/router.js`
- Create: `web/src/pages/Corpora.vue`、`CorpusDetail.vue`、`Chunks.vue`、`Search.vue`、`Ontology.vue`、`Entities.vue`、`Pending.vue`、`Graph.vue`、`Stats.vue`
- Modify: `docker-compose.yml`（追加 web service）

**Interfaces:**
- Consumes: Task 10 的全部端点。
- Produces: 宿主 `http://127.0.0.1:8100` 的管理界面，容器内 nginx 反代 `/api/`、`/retrieval`、`/mcp` 到 `api:8101`；令牌存于 `localStorage` 键 `kb_token`，首次访问弹窗输入。

- [ ] **Step 1: 写 package.json 与 vite.config.js**

`web/package.json`：

```json
{
  "name": "center-kb-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "element-plus": "^2.8.0",
    "vis-network": "^9.1.9",
    "vis-data": "^7.1.9",
    "vue": "^3.5.0",
    "vue-router": "^4.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.1.0",
    "vite": "^5.4.0"
  }
}
```

`web/vite.config.js`：

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: { outDir: 'dist' },
  server: {
    port: 8100,
    proxy: { '/api': { target: 'http://127.0.0.1:8101', changeOrigin: true } }
  }
})
```

- [ ] **Step 2: 写 index.html、main.js、api.js、router.js**

`web/index.html`：

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>中心知识库</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

`web/src/main.js`：

```javascript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

createApp(App).use(ElementPlus).use(router).mount('#app')
```

`web/src/api.js`：

```javascript
export function token() {
  let value = localStorage.getItem('kb_token')
  if (!value) {
    value = window.prompt('请输入访问令牌') || ''
    if (value) localStorage.setItem('kb_token', value)
  }
  return value
}

async function call(path, options = {}) {
  const resp = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token()}`,
      ...(options.headers || {})
    }
  })
  if (resp.status === 401) {
    localStorage.removeItem('kb_token')
    throw new Error('令牌无效，请重新输入')
  }
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) throw new Error(body?.error?.message || resp.statusText)
  return body.data
}

export const api = {
  get: (path) => call(path),
  post: (path, payload) => call(path, { method: 'POST', body: JSON.stringify(payload) }),
  patch: (path, payload) => call(path, { method: 'PATCH', body: JSON.stringify(payload) }),
  del: (path) => call(path, { method: 'DELETE' }),
  raw: (path) => call(path).then(() => fetch(path, { headers: { Authorization: `Bearer ${token()}` } }))
}
```

`web/src/router.js`：

```javascript
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/corpora' },
  { path: '/corpora', name: 'corpora', component: () => import('./pages/Corpora.vue') },
  { path: '/corpora/:id', name: 'corpus', component: () => import('./pages/CorpusDetail.vue') },
  { path: '/corpora/:id/chunks', name: 'chunks', component: () => import('./pages/Chunks.vue') },
  { path: '/search', name: 'search', component: () => import('./pages/Search.vue') },
  { path: '/ontology/:id', name: 'ontology', component: () => import('./pages/Ontology.vue') },
  { path: '/entities/:id', name: 'entities', component: () => import('./pages/Entities.vue') },
  { path: '/pending', name: 'pending', component: () => import('./pages/Pending.vue') },
  { path: '/graph/:id', name: 'graph', component: () => import('./pages/Graph.vue') },
  { path: '/stats/:id', name: 'stats', component: () => import('./pages/Stats.vue') }
]

export default createRouter({ history: createWebHistory(), routes })
```

- [ ] **Step 3: 写 App.vue 与检索页（完整参考实现）**

`web/src/App.vue`：

```vue
<template>
  <el-container>
    <el-aside width="180px">
      <el-menu router :default-active="$route.path">
        <el-menu-item index="/corpora">库管理</el-menu-item>
        <el-menu-item index="/search">检索测试</el-menu-item>
        <el-menu-item index="/pending">待处理队列</el-menu-item>
      </el-menu>
    </el-aside>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>
```

`web/src/pages/Search.vue`：

```vue
<template>
  <div>
    <el-form inline>
      <el-form-item label="库">
        <el-select v-model="form.corpus_id" style="width: 200px">
          <el-option v-for="c in corpora" :key="c.corpus_id" :label="c.name" :value="c.corpus_id" />
        </el-select>
      </el-form-item>
      <el-form-item label="查询">
        <el-input v-model="form.query" style="width: 360px" @keyup.enter="run" />
      </el-form-item>
      <el-form-item label="条数">
        <el-input-number v-model="form.top_k" :min="1" :max="50" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="run">检索</el-button>
      </el-form-item>
    </el-form>

    <el-form inline>
      <el-form-item label="标签过滤">
        <el-input v-model="tags" placeholder="逗号分隔" style="width: 200px" />
      </el-form-item>
      <el-form-item label="类型过滤">
        <el-input v-model="classIri" placeholder="类 IRI，留空不过滤" style="width: 300px" />
      </el-form-item>
    </el-form>

    <el-table :data="results" border>
      <el-table-column prop="fused_rank" label="融合排名" width="90" />
      <el-table-column prop="vector_rank" label="向量排名" width="90" />
      <el-table-column prop="score" label="分数" width="90" />
      <el-table-column label="命中片段">
        <template #default="{ row }">
          <div>{{ row.content }}</div>
          <el-tag size="small">{{ row.asset_rel_path }} #{{ row.anchor.seq }}</el-tag>
          <el-tag v-for="h in row.heading_path" :key="h" size="small" type="info">{{ h }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上下文">
        <template #default="{ row }">
          <el-popover width="520" trigger="click">
            <template #reference><el-link>展开</el-link></template>
            <pre style="white-space: pre-wrap">{{ row.context }}</pre>
          </el-popover>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'

const corpora = ref([])
const results = ref([])
const loading = ref(false)
const tags = ref('')
const classIri = ref('')
const form = ref({ corpus_id: '', query: '', top_k: 10 })

onMounted(async () => {
  corpora.value = await api.get('/api/v1/corpora')
  if (!form.value.corpus_id && corpora.value.length) {
    form.value.corpus_id = corpora.value[0].corpus_id
  }
})

async function run() {
  loading.value = true
  try {
    results.value = await api.post('/api/v1/search', {
      ...form.value,
      filters: {
        tags: tags.value ? tags.value.split(',').map((t) => t.trim()) : [],
        class_iri: classIri.value.trim() || undefined
      }
    })
  } catch (err) {
    ElMessage.error(err.message)
  } finally {
    loading.value = false
  }
}
</script>
```

- [ ] **Step 4: 实现其余七个页面**

每页的元素与数据来源固定如下，全部通过 `api.js` 调用 Task 10 的端点，不在前端做任何业务判断：

| 页面 | 端点 | 必备元素 |
| --- | --- | --- |
| Corpora.vue | GET/POST /api/v1/corpora、DELETE 单条 | 库表格（名称、子目录、模型、维度、图扩展开关、归档状态）；新建表单含全部字段（含 graph_expand_enabled 与 graph_weight）；删除按钮二次确认；每行跳转详情、本体、实体、图谱、统计五个入口 |
| CorpusDetail.vue | GET /api/v1/corpora/{id}、POST /{id}/sync、POST /{id}/rebuild/estimate、POST /{id}/rebuild、GET /tasks/{task_id} | 库详情卡片（含点数）；同步按钮触发后轮询任务状态直至 done/partial/failed；展示 doc_total、doc_changed、doc_removed、chunks、tokens、embed_retries、cost_estimate、error_code；重建区两个入口：结构重建（说明不产生嵌入费用）、全量重嵌入（先调 estimate 展示切片数、请求条数与费用估算，二次确认后提交并轮询任务）；嵌入模型与维度只读展示，更换提示走新建库流程 |
| Chunks.vue | GET /api/v1/corpora/{id}/assets、GET /api/v1/corpora/{id}/assets/{rel_path}/chunks | 文档表格（相对路径、哈希、修改时间、同步状态）；点击展开切片树，显示 seq、标题路径、字符数、chunk_sha256 与切片正文 |
| Ontology.vue | GET/POST/PATCH/DELETE /api/v1/ontology 各端点、GET /ontology/export/{id} | 类树（含 parent_iris 层级）、对象属性表、数据属性表；新增表单字段与 schemas 一致；支持修改与删除（删除前展示受影响实例/关系数量并要求确认）；提交失败时把 error.message 中的违规原因逐条列出；导出按钮下载 TTL |
| Entities.vue | GET/POST /api/v1/entities、POST /entities/merge、POST /entities/split、POST /relations | 实体表（label、class_iri、锚点数）；勾选两行触发合并并显示合并后锚点数；选择实体与其锚点子集发起拆分（新名称、可选类 IRI）；新建关系表单选择起点、终点、对象属性 IRI、证据锚点，violations 非空时展示违规原因并提示已转待处理队列 |
| Pending.vue | GET /api/v1/pending、POST /pending/{pid}/resolve | 队列按 kind 分组（proposal、violation、embed_failed）；每条显示 payload 摘要与尝试次数；confirm、reject、retype 三个动作，retype 需选择类 IRI |
| Graph.vue | GET /api/v1/graph?entity_id=&depth= | vis-network 画布，节点按 class_iri 着色，边标签为 type_iri；深度切换 1 或 2；画布不提供新建或拖拽连线能力 |
| Stats.vue | GET /api/v1/stats/corpus/{id} | 任务数、累计令牌、嵌入重试次数、累计费用估算、失败任务数、待处理积压数六个指标卡 |

- [ ] **Step 5: 写 web/nginx.conf 与 web/Dockerfile**

`web/nginx.conf`：

```nginx
server {
    listen 8100;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://api:8101;
        proxy_set_header Host $host;
    }

    location /retrieval {
        proxy_pass http://api:8101;
        proxy_set_header Host $host;
    }

    location /mcp {
        proxy_pass http://api:8101;
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

`web/Dockerfile`：

```dockerfile
FROM docker.m.daocloud.io/node:20-alpine AS build
WORKDIR /build
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM docker.m.daocloud.io/nginx:alpine
COPY --from=build /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8100
```

- [ ] **Step 6: 在 docker-compose.yml 追加 web**

```yaml
  web:
    build: ./web
    container_name: kb-web
    ports:
      - "127.0.0.1:8100:8100"
    depends_on: [api]
    restart: unless-stopped
```

- [ ] **Step 7: 构建启动并做浏览器校验**

```bash
cd web && npm install --no-audit --no-fund && npm run build && cd ..
docker compose up -d --build web
sleep 5
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8100/
```

Expected: `200`。

随后用 browser-use MCP 做界面断言：`mcp__browser-use__navigate_page` 打开 `http://127.0.0.1:8100/`，在弹出的令牌输入框填入 `.env` 中的 `KB_AUTH_TOKEN`，再用 `evaluate_script` 断言左侧导航含「库管理」「检索测试」「待处理队列」三项、库表格可加载。静态资源若未更新，用 `reload` 加 `ignoreCache` 强取。

- [ ] **Step 8: 提交**

```bash
git add web docker-compose.yml
git commit -m "feat: add vue management ui with nginx proxy and graph browsing"
```

---

### Task 12: 对外适配（Dify 外部知识库与 MCP）

落实：FR-12，requirements-spec.md 第 4.2、4.3 节；闭环 concept.md 第 10 节待确认第 2 项。

**Files:**
- Create: `app/kb/adapters/dify.py`、`app/kb/adapters/mcp.py`
- Create: `docs/research/dify-external-kb.md`
- Modify: `app/kb/main.py`
- Create: `app/tests/test_adapters.py`

**Interfaces:**
- Consumes: `kb.search.run_search`、`kb.graph_view.read_graph_data`、`kb.neo4j_store.get_ontology`、`kb.auth.require_token`。
- Produces:
  - `POST /retrieval`（Dify 契约，响应不带 `data` 包装）。
  - `/mcp` 流式 HTTP 端点，工具 `kb_search`、`kb_graph_query`、`kb_ontology_export`；以令牌中间件与 HTTP、Dify 契约共用同一校验分支（NFR-06）。
  - 三类调用方共用 `kb.search.run_search` 与 `kb.graph_view.read_graph_data`，不存在第二份检索编排实现。

- [ ] **Step 1: 实测确认 Dify 外部知识库契约**

用 WebFetch 读取 Dify 官方文档中「外部知识库 API」页面，确认端点方法、请求头、请求与响应字段名、错误约定，写入 `docs/research/dify-external-kb.md`，固定章节为：端点与方法、鉴权头、请求字段、响应字段、错误约定、与本机 1.17.1 的差异。若与本节 Step 3 的实现不一致，以实测结果为准修订实现并同步修订 requirements-spec.md 第 4.2 节。

- [ ] **Step 2: 写失败测试 app/tests/test_adapters.py**

```python
import pytest
from fastapi.testclient import TestClient

from kb.main import create_app

HEADERS = {"Authorization": "Bearer test-token"}

FAKE_RESULTS = [
    {
        "chunk_id": "cid1",
        "content": "命中片段",
        "context": "所属小节的完整上下文",
        "anchor": {"rel_path": "acc/a.md", "seq": 0, "sha256": "s0"},
        "score": 0.42,
        "vector_rank": 1,
        "fused_rank": 1,
        "heading_path": ["标题"],
        "asset_rel_path": "acc/a.md",
    }
]


@pytest.fixture
def client(monkeypatch):
    async def fake_search(settings, corpus_id, query, filters, top_k):
        assert corpus_id == "corp1"
        assert query == "测试查询"
        return FAKE_RESULTS

    monkeypatch.setattr("kb.adapters.dify.run_search", fake_search)
    return TestClient(create_app())


def test_retrieval_returns_dify_shape(client):
    resp = client.post(
        "/retrieval",
        headers=HEADERS,
        json={
            "knowledge_id": "corp1",
            "query": "测试查询",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.0},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "data" not in body
    record = body["records"][0]
    assert record["content"] == "所属小节的完整上下文"
    assert record["title"] == "acc/a.md"
    assert record["metadata"]["chunk_id"] == "cid1"
    assert record["metadata"]["anchor"]["sha256"] == "s0"


def test_retrieval_applies_score_threshold(client):
    resp = client.post(
        "/retrieval",
        headers=HEADERS,
        json={
            "knowledge_id": "corp1",
            "query": "测试查询",
            "retrieval_setting": {"top_k": 5, "score_threshold": 0.9},
        },
    )
    assert resp.json()["records"] == []


def test_retrieval_requires_token(client):
    resp = client.post("/retrieval", json={"knowledge_id": "corp1", "query": "q"})
    assert resp.status_code == 401


def test_mcp_requires_token(client):
    resp = client.get("/mcp")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_mcp_accepts_token(client):
    assert client.get("/mcp", headers=HEADERS).status_code in (200, 406)
```

- [ ] **Step 3: 写 app/kb/adapters/dify.py**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from kb.auth import require_token
from kb.config import get_settings
from kb.search import run_search

router = APIRouter(dependencies=[Depends(require_token)])


class RetrievalSetting(BaseModel):
    top_k: int = 10
    score_threshold: float | None = None


class RetrievalRequest(BaseModel):
    knowledge_id: str
    query: str
    retrieval_setting: RetrievalSetting = RetrievalSetting()


@router.post("/retrieval")
async def retrieval(body: RetrievalRequest) -> dict:
    results = await run_search(
        get_settings(),
        body.knowledge_id,
        body.query,
        {},
        body.retrieval_setting.top_k,
    )
    threshold = body.retrieval_setting.score_threshold or 0.0
    records = [
        {
            "content": item["context"] or item["content"],
            "score": item["score"],
            "title": item["asset_rel_path"],
            "metadata": {
                "source": item["asset_rel_path"],
                "chunk_id": item["chunk_id"],
                "anchor": item["anchor"],
                "heading_path": item["heading_path"],
            },
        }
        for item in results
        if item["score"] >= threshold
    ]
    return {"records": records}
```

- [ ] **Step 4: 写 app/kb/adapters/mcp.py**

```python
from pathlib import Path

from fastapi.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

from kb.config import get_settings
from kb.graph_view import read_graph_data
from kb.neo4j_store import get_driver, get_ontology
from kb.ontology import export_ttl
from kb.search import run_search

mcp = FastMCP("center-kb")


class MCPTokenMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            expected = f"Bearer {get_settings().kb_auth_token}".encode("utf-8")
            headers = dict(scope["headers"])
            if headers.get(b"authorization") != expected:
                response = JSONResponse(
                    {"error": {"code": "AUTH_REQUIRED", "message": "缺少或无效的访问令牌"}},
                    status_code=401,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


@mcp.tool()
async def kb_search(query: str, corpus_id: str, top_k: int = 10) -> list[dict]:
    """在中心知识库中做语义检索，返回命中片段、上下文与锚点。"""
    return await run_search(get_settings(), corpus_id, query, {}, top_k)


@mcp.tool()
def kb_graph_query(entity_id: str, depth: int = 2) -> dict:
    """按实体标识展开知识图谱，返回节点与边。"""
    settings = get_settings()
    driver = get_driver(settings)
    try:
        return read_graph_data(driver, entity_id, depth)
    finally:
        driver.close()


@mcp.tool()
def kb_ontology_export(corpus_id: str) -> str:
    """返回指定库的本体 TTL 文本。"""
    settings = get_settings()
    driver = get_driver(settings)
    path = Path(settings.kb_ontology_export_dir) / f"{corpus_id}.ttl"
    try:
        export_ttl(get_ontology(driver, corpus_id), str(path))
    finally:
        driver.close()
    return path.read_text(encoding="utf-8")
```

- [ ] **Step 5: 修改 app/kb/main.py 挂载适配层**

在 imports 中加入：

```python
from kb.adapters import dify as dify_adapter
from kb.adapters import mcp as mcp_adapter
```

在 `create_app` 内、七个 router 之后加入：

```python
    app.include_router(dify_adapter.router)
    app.mount("/mcp", mcp_adapter.MCPTokenMiddleware(mcp_adapter.mcp.streamable_http_app()))
```

若已安装的 mcp SDK 版本不提供 `streamable_http_app()`，改用该版本对应的 HTTP 传输挂载方法，工具定义与令牌中间件不变。MCP 客户端须携带 `Authorization: Bearer <KB_AUTH_TOKEN>` 请求头。

- [ ] **Step 6: 运行测试**

```bash
cd app && set -a && . ../.env && set +a && KB_AUTH_TOKEN=test-token .venv/Scripts/python -m pytest tests/test_adapters.py -q
```

Expected: 5 passed。

- [ ] **Step 7: 容器内实测两个端点**

```bash
docker compose up -d --build api
TOKEN=$(grep '^KB_AUTH_TOKEN=' .env | cut -d= -f2)
curl -s -X POST http://127.0.0.1:8101/retrieval -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"knowledge_id":"<已有库ID>","query":"测试","retrieval_setting":{"top_k":3}}'
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8101/mcp
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8101/mcp
```

Expected: 第一条返回含 `records` 数组的 JSON；第二条返回 401（无令牌）；第三条返回非 401（流式端点对普通 GET 的重定向与 404 等行为以 mcp SDK 版本为准）。

- [ ] **Step 8: 打通 Dify 与 center-kb 的 Docker 网络并注册（需人工操作）**

按 NFR-06，Dify 走 Docker 网络内服务名、不经过宿主端口。先建立共享网络并接入 Dify 编排的 api 容器：

```bash
docker network create kb-shared
docker network connect kb-shared <Dify 编排中 api 容器的名称或 ID>
```

在 docker-compose.yml 的 api service 下增加一行 `networks: [default, kb-shared]`，并在文件末尾追加：

```yaml
networks:
  kb-shared:
    external: true
```

```bash
docker compose up -d api
```

随后在 Dify 界面「知识库 → 外部知识库 API」中登记：端点 `http://api:8101`，API Key 填 `.env` 中的 `KB_AUTH_TOKEN`，knowledge_id 填库标识。登记与一次真实问答验证由用户执行，结果记入 `docs/acceptance/records.md` 的 V10 条目。仅当用户不接受对 Dify 容器做网络改动时，才退回 `http://host.docker.internal:8101`，且必须把这一偏离记入 records.md 的 NFR-06 条目。

- [ ] **Step 9: 提交**

```bash
git add app/kb/adapters app/kb/main.py app/tests/test_adapters.py docs/research/dify-external-kb.md
git commit -m "feat: add dify external knowledge adapter and mcp tools"
```

---

### Task 13: 备份与恢复

落实：FR-13、NFR-08。

**Files:**
- Create: `scripts/backup.sh`、`scripts/restore.sh`、`scripts/README.md`

**Interfaces:**
- Consumes: Task 1 的三个命名卷与 `.env`。
- Produces: `backups/<时间戳>/` 下的 `qdrant.tar.gz`、`neo4j.tar.gz`、`redis.tar.gz`、`meta.json`（含各库标识与 collection 清单）；`scripts/restore.sh <时间戳>` 的反向操作。

- [ ] **Step 1: 写 scripts/backup.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

STAMP=$(date +%Y%m%d-%H%M%S)
OUT="backups/$STAMP"
mkdir -p "$OUT"

QKEY=$(grep '^QDRANT_API_KEY=' .env | cut -d= -f2)
curl -s -H "api-key: $QKEY" http://127.0.0.1:6340/collections > "$OUT/meta.json"

echo "停止全部服务以保证一致性快照"
docker compose stop

for pair in "center-kb_qdrant-data:qdrant" "center-kb_neo4j-data:neo4j" "center-kb_redis-data:redis"; do
  vol="${pair%%:*}"
  name="${pair##*:}"
  docker run --rm -v "$vol":/data -v "$(pwd)/$OUT":/backup \
    docker.m.daocloud.io/alpine:3.20 \
    tar czf "/backup/$name.tar.gz" -C /data .
  echo "已备份 $vol -> $OUT/$name.tar.gz"
done

docker compose start
echo "备份完成：$OUT"
```

collection 清单在停止容器前采集，快照在全部服务（含 Qdrant、Neo4j、Redis）停止后打包，二者顺序不可调换。

- [ ] **Step 2: 写 scripts/restore.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

STAMP="${1:?用法: scripts/restore.sh <时间戳>}"
SRC="backups/$STAMP"
[ -d "$SRC" ] || { echo "备份目录不存在: $SRC"; exit 1; }

docker compose down
for pair in "center-kb_qdrant-data:qdrant" "center-kb_neo4j-data:neo4j" "center-kb_redis-data:redis"; do
  vol="${pair%%:*}"
  name="${pair##*:}"
  docker run --rm -v "$vol":/data -v "$(pwd)/$SRC":/backup \
    docker.m.daocloud.io/alpine:3.20 \
    sh -c "rm -rf /data/* && tar xzf /backup/$name.tar.gz -C /data"
  echo "已恢复 $vol"
done
docker compose up -d
echo "恢复完成，请按 V4 判据复验"
```

- [ ] **Step 3: 写 scripts/README.md**

说明备份时机、停服窗口、恢复后必须执行的复验步骤（引用 requirements-spec.md 第 8 节 V4），以及权威源目录由版本库单独保障、不在本脚本范围内。

- [ ] **Step 4: 赋可执行权限并跑一次备份**

```bash
chmod +x scripts/backup.sh scripts/restore.sh
./scripts/backup.sh
ls -la backups/*/
```

Expected: 三个 tar.gz 与 meta.json 存在且非空。

- [ ] **Step 5: 提交**

```bash
git add scripts
git commit -m "feat: add volume backup and restore scripts"
```

---

### Task 14: 全链路验收（V1 至 V10）

落实：requirements-spec.md 第 8 节全部判据；FR-11 的性能记录。

**Files:**
- Create: `scripts/make_acceptance_corpus.py`
- Create: `docs/acceptance/records.md`

**Interfaces:**
- Consumes: 全部前序任务的端点与容器。
- Produces: `knowledge-lib-base-folder/acceptance/` 下 200 篇验收语料与逐条判据的执行记录。

- [ ] **Step 1: 写语料生成脚本 scripts/make_acceptance_corpus.py**

```python
"""生成 200 篇验收语料到 knowledge-lib-base-folder/acceptance/。

每篇含：唯一可检索表述、两个标签、至少一个本体类别名，
其中三篇共享同一别名以支撑 V8 的多锚点判据。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "knowledge-lib-base-folder" / "acceptance"
TOTAL = 200
SHARED_ALIAS = "验收项目组"
SHARED_INDEXES = (3, 47, 121)


def note(index: int) -> str:
    tags = ["验收", "批次一" if index % 2 == 0 else "批次二"]
    alias = SHARED_ALIAS if index in SHARED_INDEXES else f"专题{index:03d}"
    return f"""---
tags: {tags}
---

# 验收笔记 {index:03d}

## 概述

唯一表述标识符 ACCEPT-{index:04d}-UNIQUE 出现在本节，用于检索命中判定。

## 关联

本节涉及{alias}，其职责范围与交付边界在本篇内描述。

## 结论

第 {index} 篇的结论段落，供上下文回读校验。
"""


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for index in range(1, TOTAL + 1):
        (ROOT / f"note-{index:03d}.md").write_text(note(index), encoding="utf-8")
    print(f"已生成 {TOTAL} 篇到 {ROOT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 生成语料并建库**

```bash
python scripts/make_acceptance_corpus.py
ls knowledge-lib-base-folder/acceptance | wc -l
TOKEN=$(grep '^KB_AUTH_TOKEN=' .env | cut -d= -f2)
CORPUS=$(curl -s -X POST http://127.0.0.1:8101/api/v1/corpora \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"验收库","subdir":"acceptance","ontology_prefix":"acc","vector_dim":1024}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['data']['corpus_id'])")
echo "corpus_id=$CORPUS"
```

- [ ] **Step 3: 建本体类与别名（支撑 V5、V6、V8）**

```bash
curl -s -X POST "http://127.0.0.1:8101/api/v1/ontology/classes?corpus_id=$CORPUS" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"iri":"http://kb.local/o/acc#Project","prefix_local":"Project","label_zh":"项目","definition":"一个交付单元","aliases":["验收项目组"]}'
curl -s -X POST "http://127.0.0.1:8101/api/v1/ontology/classes?corpus_id=$CORPUS" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"iri":"http://kb.local/o/acc#Person","prefix_local":"Person","label_zh":"人员","definition":"参与交付的个体"}'
curl -s -X POST "http://127.0.0.1:8101/api/v1/ontology/object-properties?corpus_id=$CORPUS" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"iri":"http://kb.local/o/acc#belongsTo","prefix_local":"belongsTo","label_zh":"属于","definition":"人员从属于项目","domain_iri":"http://kb.local/o/acc#Person","range_iri":"http://kb.local/o/acc#Project"}'
```

- [ ] **Step 4: 执行 V1 并记录实测值**

开始前确认 `DASHSCOPE_API_KEY` 已在当前终端 export，并执行 `docker compose up -d worker` 使其进入 worker 容器（compose 从当前 shell 读取该变量注入）。

```bash
TASK=$(curl -s -X POST "http://127.0.0.1:8101/api/v1/corpora/$CORPUS/sync" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"scope":"all"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['task_id'])")
while :; do
  S=$(curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8101/api/v1/tasks/$TASK)
  echo "$S" | python -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['status'],d['doc_total'],d['doc_changed'],d['chunks'],d['tokens'],d['cost_estimate'])"
  echo "$S" | grep -q '"status":"done"' && break
  sleep 10
done
curl -s -X POST http://127.0.0.1:8101/api/v1/search -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"corpus_id\":\"$CORPUS\",\"query\":\"ACCEPT-0042-UNIQUE\",\"top_k\":3}" \
  | python -m json.tool | head -40
```

Expected: `doc_total=200`；检索首条结果的 `anchor.rel_path` 为 `note-042.md`、`seq` 指向「概述」小节，`context` 与文件内容逐字一致。记录同步总耗时、令牌数与费用估算到 `docs/acceptance/records.md` 的 V1 条目。

- [ ] **Step 5: 执行 V2 幂等**

```bash
TASK2=$(curl -s -X POST "http://127.0.0.1:8101/api/v1/corpora/$CORPUS/sync" \
  -H "Authorization: Bearer $TOKEN" -d '{"scope":"all"}' -H "Content-Type: application/json" \
  | python -c "import sys,json;print(json.load(sys.stdin)['data']['task_id'])")
sleep 15
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8101/api/v1/tasks/$TASK2
```

Expected: `doc_changed=0`、`tokens=0`、`cost_estimate=0`。随后修改 `note-007.md` 正文再同步一次，Expected: `doc_changed=1` 且点数不增长（用 `GET /api/v1/corpora/$CORPUS` 的 points 字段前后对比）。

- [ ] **Step 6: 执行 V3 双索引一致**

取 Step 4 检索结果中任一条，核对三处：向量载荷锚点（检索响应的 `anchor`）、Neo4j 实体锚点（`GET /api/v1/entities?corpus_id=$CORPUS` 中对应实体的 `anchors`）、权威源文件路径与行号。Expected: 三者指向同一切片；Neo4j 实体节点无正文字段。

- [ ] **Step 7: 执行 V5 与 V6**

```bash
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8101/api/v1/ontology/export/$CORPUS" -o /tmp/acc.ttl
head -30 /tmp/acc.ttl
```

Expected: TTL 含完整 IRI、`rdfs:label` 与 `rdfs:comment`、`belongsTo` 的 `rdfs:domain` 与 `rdfs:range`。用户以 Protégé 打开该文件确认无解析错误，结果记入 records.md。

V6：先建一个 Person 实体与一个 Project 实体并建立 `belongsTo` 关系，再把 `belongsTo` 的 `range_iri` 改为 `http://kb.local/o/acc#Person` 重新提交，Expected: 响应 `violations` 非空且原关系出现在 `GET /api/v1/pending` 中，无静默丢弃。

- [ ] **Step 8: 执行 V7 与 V8**

V7：构造一条与查询词无关但通过已确认关系相连的切片，分别在库配置 graph_expand_enabled 为 true 与 false 时检索同一查询（两次检索之间用 PATCH /api/v1/corpora/{id} 修改配置），Expected: true 时该条进入结果集且 `vector_rank` 为 null、`fused_rank` 有值，false 时不进入。

V8：确认 `GET /api/v1/pending` 中存在三个来自 `note-003.md`、`note-047.md`、`note-121.md` 的「验收项目组」提案；逐条 confirm 后 Expected: 三条提案归并为同一 `eid`，该实体 `anchors` 长度为 3，且此后检索可被图谱扩展命中。

V8 补充（FR-09 拆分）：对合并后的三锚点实体执行 `POST /api/v1/entities/split`，把 1 个锚点拆为 `new_label` 为「验收项目组-子」的新实体，Expected: 原实体剩 2 个锚点、新实体 1 个锚点，锚点总数不变。

- [ ] **Step 9: 执行 V9 访问与密钥边界**

```bash
ipconfig | grep -E "IPv4" | head -3
LAN_IP=<上一步得到的局域网地址>
curl -s -m 3 http://$LAN_IP:8100/ || echo "局域网不可达（预期）"
docker logs kb-api kb-worker 2>&1 | grep -i "$DASHSCOPE_API_KEY" && echo "密钥泄漏" || echo "日志无密钥"
[ -d web/dist ] && grep -r "$(grep '^KB_AUTH_TOKEN=' .env | cut -d= -f2)" ontology web/dist 2>/dev/null && echo "导出物含令牌" || echo "导出物无令牌"
```

Expected: 局域网地址访问超时或拒绝；日志与导出物中均检索不到密钥与令牌。随后关闭本机代理持久会话（xrelay），重跑一次单文件同步，Expected: 任务状态为 done，验证 NFR-04。

- [ ] **Step 10: 执行 V4 整库重建**

```bash
./scripts/backup.sh
docker compose down
docker volume rm center-kb_qdrant-data center-kb_neo4j-data center-kb_redis-data
docker compose up -d
```

Expected: 卷删除后系统空库启动。随后仅凭权威源目录重新建库、建本体（Step 2 与 Step 3 的命令重放）并触发同步，复现 V1 与 V3 判据；记录重嵌入的令牌数与耗时。也可改用 `scripts/restore.sh <时间戳>` 直接还原并复验，两种方式都需在 records.md 中记录。

补充验证界面重建入口（FR-13）：结构重建 `POST /corpora/$CORPUS/rebuild/estimate` 与 `POST /corpora/$CORPUS/rebuild`（mode=structure），Expected: 任务 kind=rebuild、状态 done、tokens=0（不产生嵌入请求），检索 V1 判据复现。全量重嵌入：先 `GET /corpora/$CORPUS/rebuild/estimate` 确认返回预估切片数与嵌入请求条数，界面二次确认后 `POST /corpora/$CORPUS/rebuild`（mode=reembed），Expected: 任务 done 且 V1、V3 复现，记录令牌数与耗时。嵌入模型或维度变更流程（可选）：新建库指向同一权威源子目录 → 同步 → 验证通过后归档旧库，过程记入 records.md。

- [ ] **Step 11: 执行 V10 对外接口一致性**

对同一条查询分别发起三种调用：界面检索、`POST /retrieval`（Dify 契约）、MCP `kb_search`。Expected: 三者返回的正文、分数与锚点字段一致；用 `grep -rn "run_search" app/kb` 确认检索编排实现只有一处。

- [ ] **Step 12: 写验收记录并提交**

`docs/acceptance/records.md` 按 V1 至 V10 分节，每节记录：执行时间、命令或操作、实测输出摘要、结论（通过/不通过）、不通过项的原因与处置。

```bash
git add scripts/make_acceptance_corpus.py docs/acceptance/records.md
git commit -m "test: add acceptance corpus generator and V1-V10 execution records"
```

验收语料保留在 `knowledge-lib-base-folder/acceptance/`，作为回归测试的固定数据集；如需清空，删除该子目录并触发一次同步即可，索引随之清理。

---

## 自审结论

**规格覆盖**：FR-01 至 FR-13 与 NFR-01 至 NFR-11 全部有对应任务。映射关系为 FR-01 → Task 6、10；FR-02 → Task 4、5、8、10；FR-03 → Task 5、10、11；FR-04 → Task 9、10、11；FR-05 → Task 5、9、10；FR-06 → Task 6、10、11；FR-07 → Task 6、10；FR-08 → Task 7、10、11；FR-09 → Task 7、10、11；FR-10 → Task 10、11；FR-11 → Task 8、10、11；FR-12 → Task 12；FR-13 → Task 8、10、11、13。NFR-01 至 NFR-05 → Task 3、5、8；NFR-06、NFR-07 → Task 1、2、11、12；NFR-08 → Task 1、13；NFR-09 → Task 8、10、11；NFR-10 → Task 14；NFR-11 → Task 1。验收判据 V1 至 V10 → Task 14。

**执行顺序依赖**：Task 0 → 1 → 2 → 3、4、5 可并行 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14。其中 6 依赖 2，7 依赖 6，8 依赖 3、4、5、7，9 依赖 5、6，10 依赖 6 至 9，11 依赖 10，12 依赖 9、10，14 依赖全部。

**类型一致性**：`chunk_id(rel_path, chunk_sha)`、`build_payload(...)`、`scan_assets(root, targets)`、`run_sync(settings, corpus_id, scope, file_path)`、`run_rebuild(settings, corpus_id, mode)`、`estimate_rebuild(settings, corpus_id)`、`run_search(settings, corpus_id, query, filters, top_k)`、`rrf_fuse(ranked_lists, k, weights)`、`class_matched_pairs(driver, corpus_id, payloads, iris)`、`read_graph_data(driver, entity_id, depth)`、`resolve_pending(driver, pid, action, new_class_iri)`、`ensure_entity(driver, corpus_id, label, class_iri, anchor, ont_version)`、`split_entity(driver, eid, new_label, anchors, class_iri)`、`find_entities_by_anchor_rel_path(driver, corpus_id, rel_path)`、`embed_with_retry(settings, texts) -> (向量, 令牌, 重试次数)`、`check_relation_valid(classes, obj_prop, from_class_iri, to_class_iri)`、`list_asset_rel_paths(client, corpus_id)` 在各任务间签名一致；`asset` 字典字段（rel_path、sha256、mtime）与 `chunk` 字典字段（asset_rel_path、seq、chunk_sha256、text）在 Task 5、7、8 间一致；任务状态取值 running、done、partial、failed 与任务 kind 取值 sync、rebuild 在 Task 6、8、10、11 间一致；错误信封统一为 `{"error": {"code", "message"}}`（422 校验错误保留 FastAPI 默认结构），HTTP、Dify 契约与 MCP 共用令牌校验。

**执行前须先解决的两项外部输入**：`DASHSCOPE_API_KEY` 需向用户索取（Task 3 Step 1、Task 14 全程）；Dify 界面侧的外部知识库注册需用户手工完成（Task 12 Step 8）。

**本目录尚未初始化版本库**：Task 0 的 Step 3 负责初始化；若用户不采用版本库，全部 commit 步骤跳过，其余步骤与验收不受影响。

## 实施修正记录

以下修正为实施过程中基于实测环境作出的必要调整，与上文代码块存在差异处以此节为准：

1. **锚点建模改为 `(:Anchor)` 节点**（Task 6、7、9、10）：Neo4j 属性只允许基本类型数组，不支持对象数组，`Entity.anchors` 无法作为属性存储。锚点改为 `(:Anchor {rel_path, seq, sha256})` 节点（复合唯一约束），经 `(:Entity)-[:ANCHOR_OF]->(:Anchor)` 关联；实体节点不再持有 anchors 属性。neo4j_store 新增 `ensure_anchor_link`、`list_entity_anchors`、`count_entity_anchors`、`move_anchors_to`、`remove_anchor_links`、`list_entities_with_anchors`；proposals 的 `ensure_entity`、`find_entities_by_anchor_rel_path`、`split_entity` 与 search 的 `EXPAND_QUERY`、`CLASS_MATCH_QUERY`、graph_view 的锚点计数均改为经锚点节点查询。Relation 的 `evidence_anchors` 以 JSON 字符串存储。
2. **本体 IRI 路由使用 `{iri:path}` 转换器**（Task 10）：`/ontology/classes/{iri}` 等六个读写路由改为 `{iri:path}`，避免 IRI 中编码的 `/` 破坏路径匹配。
3. **变更资产先删旧点再写入**（Task 8）：全量同步中，内容变更的资产在 upsert 新切片前先按 rel_path 删除旧点位，保证 V2 判据「点数不增长」。
4. **测试隔离**：test_sync 以 monkeypatch 替换 `kb.sync.embed_with_retry`（respx 的 side_effect 响应缺少 content-type，return_value 风格保留在 test_embed）；同步集成测试开始前清理同名库与 collection；test_api 中创建实体的测试使用唯一标签（entity_id 为确定性哈希，跨运行残留会导致串库）。
5. **版本锁定**：`mcp>=1.2,<2`（v2 移除 FastMCP 且 API 变更）；`openai>=1.40,<2`（3.x 自带 fork 的 httpx，respx 无法拦截）；respx 测试默认 `assert_all_mocked` 会拦截 Qdrant 等真实请求，sync 测试改用函数替换方案。
6. **构建期网络**：宿主机与容器内 pip 直连缓慢或挂起，app/Dockerfile 的 `pip install` 显式使用清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`；宿主机 venv 安装加 `--no-cache-dir --no-build-isolation`（pip 写本地 HTTP 缓存在本机挂起）。
7. **MCP 端点普通 GET 行为**：流式端点对无 Accept 头的 GET 返回 307/404 而非 200/406，Task 12 Step 7 的预期已改为「非 401」。
8. **MCP 挂载集成**（Task 12）：FastMCP 的 `streamable_http_app()` 内部路由写死 `/mcp` 且自带 lifespan，直接 `app.mount("/mcp", ...)` 会得到 /mcp/mcp 路由并丢失会话管理器生命周期。实现改为：`mcp.settings.streamable_http_path = "/"`、每个 `create_app()` 实例经 `build_streamable_app()` 创建子应用与 session_manager，FastAPI lifespan 内 `async with session_manager.run()`，再 mount 到 `/mcp`。MCP 客户端须以 `/mcp/`（尾斜杠）访问。
9. **Qdrant 点 ID 归一化**：upsert 用纯 hex 前缀（32 位），Qdrant 返回带连字符的 UUID 字符串；检索融合与结构重建的 `by_id` 查找统一 `replace("-", "")` 归一化。
10. **`fetch_points` 返回向量**：qdrant `retrieve` 默认 `with_vectors=False`，结构重建需要向量，已显式 `with_vectors=True`。
11. **retrieve 上下文路径**：`run_search` 回源读文件须拼接库子目录（`kb_corpus_root / corpus.subdir`），否则锚点相对路径定位失败。
12. **对象属性保存即入队违规**：create/patch object-properties 除返回 violations 外，将违规关系以 kind=violation 写入待处理队列（FR-07）。
13. **同步/重建任务 ID 与 arq 对齐**：`run_sync`/`run_rebuild` 接受外部 task_id，worker 传入 `ctx["job_id"]`，保证 API 返回的任务标识即任务记录 ID。
14. **测试隔离与 Windows 编码**：本机 PowerShell 命令行中文字面量会被 GBK 破坏，验收载荷一律经 UTF-8 文件注入；python 子进程在缺少 DSH 沙箱写入授权的目录（如 knowledge-lib-base-folder）无法写文件，语料生成以 PowerShell + UTF-8 模板完成。
15. **nginx 动态解析上游**（Task 11）：api 容器 `--force-recreate` 后 IP 变化，web 容器 nginx 启动时缓存的旧 IP 导致 502 Bad Gateway。nginx 配置改为 `resolver 127.0.0.11` + 变量化 `proxy_pass`，每请求动态解析 `api` 服务名。

