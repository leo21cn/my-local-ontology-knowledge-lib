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
               sum(t.extract_calls) AS extract_calls,
               sum(t.extract_tokens) AS extract_tokens,
               sum(t.extract_failed) AS extract_failed,
               sum(t.extract_cost_estimate) AS extract_cost,
               sum(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed,
               count(DISTINCT p) AS pending
        """,
        id=corpus_id,
    ).single()
    return {"data": dict(row)}
