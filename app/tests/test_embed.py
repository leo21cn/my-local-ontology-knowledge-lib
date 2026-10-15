import httpx
import pytest
import respx
from openai import APIError

from kb.config import Settings
from kb.embed import EmbedErrorCode, classify_error, embed_texts


@pytest.fixture
def settings() -> Settings:
    return Settings(kb_auth_token="t", dashscope_api_key="k", kb_embed_dim=1024)


@respx.mock
async def test_embed_texts_returns_vectors_and_tokens(settings):
    respx.post("https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1, 0.2], "index": 0}, {"embedding": [0.3, 0.4], "index": 1}],
                "usage": {"total_tokens": 8},
            },
        )
    )
    vectors, tokens = await embed_texts(settings, ["甲", "乙"])
    assert len(vectors) == 2
    assert vectors[1] == [0.3, 0.4]
    assert tokens == 8


@respx.mock
async def test_embed_texts_empty_input_skips_call(settings):
    route = respx.post("https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings")
    vectors, tokens = await embed_texts(settings, [])
    assert (vectors, tokens) == ([], 0)
    assert not route.called


def test_classify_error_arrearage_is_billing():
    exc = APIError("Arrearage: account is in arrears", request=None, body=None)
    assert classify_error(exc) == EmbedErrorCode.BILLING


def test_classify_error_unknown_is_upstream():
    assert classify_error(RuntimeError("socket closed")) == EmbedErrorCode.UPSTREAM
