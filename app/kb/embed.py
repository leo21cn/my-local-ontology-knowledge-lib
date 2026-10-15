import asyncio
from enum import Enum

from openai import APIError, AsyncOpenAI, AuthenticationError, BadRequestError, RateLimitError

from kb.config import Settings

BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
RETRY_DELAY_SECONDS = (2, 4, 8)


class EmbedErrorCode(str, Enum):
    AUTH = "AUTH"
    RATE = "RATE"
    INPUT = "INPUT"
    BILLING = "BILLING"
    UPSTREAM = "UPSTREAM"


class EmbedError(Exception):
    def __init__(self, code: EmbedErrorCode, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def classify_error(exc: Exception) -> EmbedErrorCode:
    if isinstance(exc, AuthenticationError):
        return EmbedErrorCode.AUTH
    if isinstance(exc, RateLimitError):
        return EmbedErrorCode.RATE
    if isinstance(exc, BadRequestError):
        return EmbedErrorCode.INPUT
    text = str(exc)
    for marker, code in (
        ("Arrearage", EmbedErrorCode.BILLING),
        ("InvalidApiKey", EmbedErrorCode.AUTH),
        ("Throttling", EmbedErrorCode.RATE),
        ("InvalidParameter", EmbedErrorCode.INPUT),
    ):
        if marker in text:
            return code
    return EmbedErrorCode.UPSTREAM


async def embed_texts(settings: Settings, texts: list[str]) -> tuple[list[list[float]], int]:
    if not texts:
        return [], 0
    client = AsyncOpenAI(api_key=settings.dashscope_api_key, base_url=BASE_URL, timeout=60.0)
    try:
        resp = await client.embeddings.create(
            model=settings.kb_embed_model,
            input=texts,
            dimensions=settings.kb_embed_dim,
        )
    except Exception as exc:
        raise EmbedError(classify_error(exc), str(exc)) from exc
    finally:
        await client.close()
    return [item.embedding for item in resp.data], resp.usage.total_tokens


async def embed_with_retry(settings: Settings, texts: list[str]) -> tuple[list[list[float]], int, int]:
    retries = 0
    for delay in RETRY_DELAY_SECONDS + (None,):
        try:
            vectors, tokens = await embed_texts(settings, texts)
            return vectors, tokens, retries
        except EmbedError as exc:
            retryable = exc.code in (EmbedErrorCode.RATE, EmbedErrorCode.UPSTREAM)
            if not retryable or delay is None:
                raise
            retries += 1
            await asyncio.sleep(delay)
    raise EmbedError(EmbedErrorCode.UPSTREAM, "重试次数耗尽")
