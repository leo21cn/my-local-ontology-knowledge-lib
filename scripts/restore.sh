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
