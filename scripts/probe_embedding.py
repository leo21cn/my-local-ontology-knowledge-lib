import os

from openai import OpenAI

BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = os.environ.get("KB_EMBED_MODEL", "text-embedding-v4")
client = OpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=BASE)


def probe_batch() -> None:
    for n in (1, 10, 20, 50, 100):
        try:
            resp = client.embeddings.create(model=MODEL, input=["测试文本"] * n, dimensions=1024)
            print(f"batch={n}: ok tokens={resp.usage.total_tokens}")
        except Exception as exc:
            print(f"batch={n}: FAIL {type(exc).__name__} {str(exc)[:160]}")


def probe_length() -> None:
    for chars in (500, 1000, 3000, 8000, 16000, 32000):
        try:
            resp = client.embeddings.create(model=MODEL, input="测" * chars, dimensions=1024)
            print(f"chars={chars}: ok tokens={resp.usage.total_tokens}")
        except Exception as exc:
            print(f"chars={chars}: FAIL {type(exc).__name__} {str(exc)[:160]}")


def probe_dims() -> None:
    for dim in (1024, 1536, 2048):
        try:
            resp = client.embeddings.create(model=MODEL, input=["测试"], dimensions=dim)
            print(f"dim={dim}: ok vector_len={len(resp.data[0].embedding)}")
        except Exception as exc:
            print(f"dim={dim}: FAIL {type(exc).__name__} {str(exc)[:160]}")


if __name__ == "__main__":
    probe_batch()
    probe_length()
    probe_dims()
