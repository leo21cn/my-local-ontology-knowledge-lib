import os

from arq import cron
from arq.connections import RedisSettings

from kb import sync as sync_module
from kb.config import get_settings


def poll_minutes(interval: int) -> set[int]:
    return set(range(0, 60, max(1, interval)))


async def run_sync_job(ctx, corpus_id: str, scope: str = "all",
                       file_path: str | None = None) -> str:
    return await sync_module.run_sync(
        get_settings(), corpus_id, scope, file_path, task_id=ctx.get("job_id")
    )


async def rebuild_job(ctx, corpus_id: str, mode: str) -> str:
    return await sync_module.run_rebuild(
        get_settings(), corpus_id, mode, task_id=ctx.get("job_id")
    )


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
