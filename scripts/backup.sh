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
