import asyncio
import json
import os
import time

from openai import AsyncOpenAI

BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.8-max"

SIGNATURE = {
    "classes": [
        {"iri": "http://kb.local/o/t#Project", "label": "项目", "aliases": [], "definition": "交付单元"},
        {"iri": "http://kb.local/o/t#Person", "label": "人员", "aliases": [], "definition": "个体"},
    ],
    "object_properties": [
        {"iri": "http://kb.local/o/t#belongsTo", "label": "属于",
         "domain": "http://kb.local/o/t#Person", "range": "http://kb.local/o/t#Project"},
    ],
}
TEXT = "星河项目由张三负责，张三属于星河项目。"

PROMPT = (
    "你是知识图谱抽取助手。根据给定的本体签名，从文本中抽取实体与关系。\n\n"
    "本体签名（JSON）：\n" + json.dumps(SIGNATURE, ensure_ascii=False)
    + "\n\n要求：只输出一个 JSON 对象 "
    '{"entities":[{"term":"...","class_iri":"..."}],'
    '"relations":[{"from":"...","to":"...","type_iri":"..."}]}；'
    "term 必须逐字出现在文本中；IRI 只能取签名内。\n\n文本：\n" + TEXT
)


async def call(enable_thinking):
    client = AsyncOpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"], base_url=BASE, timeout=120.0, max_retries=0
    )
    start = time.time()
    kwargs = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0,
        "max_tokens": 800,
    }
    if enable_thinking is not None:
        kwargs["extra_body"] = {"enable_thinking": enable_thinking}
    try:
        resp = await client.chat.completions.create(**kwargs)
        elapsed = time.time() - start
        tokens = resp.usage.total_tokens if resp.usage else 0
        content = (resp.choices[0].message.content or "")[:80]
        return elapsed, tokens, content, None
    except Exception as exc:
        return time.time() - start, 0, "", f"{type(exc).__name__}: {str(exc)[:100]}"
    finally:
        await client.close()


async def main():
    print(f"model={MODEL}")
    for label, flag in (("默认(不传)", None), ("关闭思考", False), ("开启思考", True)):
        elapsed, tokens, content, err = await call(flag)
        print(f"[{label}] elapsed={elapsed:.1f}s tokens={tokens} err={err}")
        if content:
            print("   content:", content)


if __name__ == "__main__":
    asyncio.run(main())
