from fastapi import APIRouter, Depends

from kb.auth import require_token
from kb.deps import get_neo4j
from kb.graph_view import read_graph_data

router = APIRouter(prefix="/api/v1/graph", dependencies=[Depends(require_token)])


@router.get("")
async def read_graph(entity_id: str, depth: int = 2, driver=Depends(get_neo4j)):
    return {"data": read_graph_data(driver, entity_id, depth)}
