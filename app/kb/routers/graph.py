from fastapi import APIRouter, Depends, HTTPException

from kb.auth import require_token
from kb.deps import get_neo4j
from kb.graph_view import read_full_graph, read_graph_data

router = APIRouter(prefix="/api/v1/graph", dependencies=[Depends(require_token)])


@router.get("")
async def read_graph(entity_id: str | None = None, depth: int = 2,
                     corpus_id: str | None = None, mode: str = "center",
                     driver=Depends(get_neo4j)):
    if mode == "all":
        if not corpus_id:
            raise HTTPException(400, detail={"code": "CORPUS_ID_REQUIRED",
                                             "message": "全部视图需要 corpus_id"})
        return {"data": read_full_graph(driver, corpus_id)}
    if not entity_id:
        raise HTTPException(400, detail={"code": "ENTITY_ID_REQUIRED",
                                         "message": "中心模式需要 entity_id"})
    return {"data": read_graph_data(driver, entity_id, depth)}
