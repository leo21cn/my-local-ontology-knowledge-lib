# 备份与恢复脚本

## 备份时机

- 建议在每次全量重嵌入、本体大规模调整或升级镜像前执行 `./scripts/backup.sh`。
- 备份会先采集 collection 清单（`meta.json`），再停止全部服务（含 Qdrant、Neo4j、Redis）以保证快照一致性，随后打包三个命名卷，最后重新启动服务。停服窗口约等于打包耗时。

## 产物

`backups/<时间戳>/` 下：

- `qdrant.tar.gz`、`neo4j.tar.gz`、`redis.tar.gz`：三个命名卷的完整快照；
- `meta.json`：备份时的 collection 清单。

## 恢复

```bash
./scripts/restore.sh <时间戳>
```

恢复脚本会 `docker compose down`、清空并解包三个命名卷、重新启动服务。恢复后必须按 requirements-spec.md 第 8 节 V4 判据复验：检索命中、双索引一致、幂等同步。

## 权威源目录

`knowledge-lib-base-folder/` 由版本库单独保障（Git 管理），不在本脚本范围内；本体 TTL 导出物（`ontology/`）同样随版本库管理。
