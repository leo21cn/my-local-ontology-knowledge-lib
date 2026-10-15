from fastapi import HTTPException, Request

from kb.config import get_settings


async def require_token(request: Request) -> None:
    expected = f"Bearer {get_settings().kb_auth_token}"
    if request.headers.get("authorization", "") != expected:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "缺少或无效的访问令牌"},
        )
