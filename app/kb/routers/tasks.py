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
