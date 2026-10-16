import json
import os

import redis

CORPUS = os.environ.get("PURGE_CORPUS_ID", "740e43f44c35")
REDIS_URL = os.environ.get("REDIS_URL")


def main() -> None:
    if not REDIS_URL:
        print("需要 REDIS_URL 环境变量")
        return
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    queue = r.zrange("arq:queue", 0, -1)
    removed = []
    kept = []
    for job_id in queue:
        data = r.hgetall(f"arq:job:{job_id}")
        function = data.get("function", "")
        args = json.loads(data.get("args", "[]"))
        if function == "induct_job" and CORPUS in args:
            r.zrem("arq:queue", job_id)
            r.delete(f"arq:job:{job_id}")
            removed.append(job_id)
        else:
            kept.append(f"{function}({args[:1]})")
    print("queued jobs before:", len(queue))
    print("removed (duplicate PM induct):", len(removed), removed)
    print("kept:", kept)


if __name__ == "__main__":
    main()
