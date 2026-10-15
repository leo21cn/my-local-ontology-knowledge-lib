import asyncio
import json
import os
import re
import time

from openai import AsyncOpenAI

BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = os.environ.get("KB_EXTRACT_MODEL", "qwen3.8-max")

SIGNATURE = {
    "classes": [
        {"iri": "http://kb.local/o/acc#Project", "label": "项目", "aliases": ["项目组"], "definition": "一个交付单元"},
        {"iri": "http://kb.local/o/acc#Person", "label": "人员", "aliases": [], "definition": "参与交付的个体"},
    ],
    "object_properties": [
        {
            "iri": "http://kb.local/o/acc#belongsTo",
            "label": "属于",
            "domain": "http://kb.local/o/acc#Person",
            "range": "http://kb.local/o/acc#Project",
        }
    ],
}

TEXT = "星河项目由张三负责，张三属于星河项目，李四也参与其中。"

PROMPT = (
    "你是知识图谱抽取助手。根据给定的本体签名，从文本中抽取实体与关系。\n\n"
    "本体签名（JSON）：\n"
    + json.dumps(SIGNATURE, ensure_ascii=False)
    + "\n\n要求：\n"
    "1. 只输出一个 JSON 对象，格式为 "
    '{"entities":[{"term":"...","class_iri":"..."}],'
    '"relations":[{"from":"...","to":"...","type_iri":"..."}]}；\n'
    "2. term/from/to 必须是文本中逐字出现的名称片段；\n"
    "3. class_iri 与 type_iri 只能取本体签名中列出的 IRI；\n"
    '4. 没有可抽取内容时输出 {"entities":[],"relations":[]}。\n\n'
    "文本：\n" + TEXT
)


async def call_once() -> tuple[str, float, int]:
    client = AsyncOpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=BASE, timeout=60.0)
    start = time.time()
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "你只输出 JSON，不输出任何其他内容。"},
                {"role": "user", "content": PROMPT},
            ],
            temperature=0,
        )
    finally:
        await client.close()
    elapsed = time.time() - start
    raw = resp.choices[0].message.content or ""
    tokens = resp.usage.total_tokens if resp.usage else 0
    return raw, elapsed, tokens


def main() -> None:
    print(f"model={MODEL}")
    for index in range(3):
        try:
            raw, elapsed, tokens = asyncio.run(call_once())
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else None
            print(
                f"run={index + 1}: ok elapsed={elapsed:.1f}s tokens={tokens} "
                f"json_valid={parsed is not None} entities={len((parsed or {}).get('entities', []))} "
                f"relations={len((parsed or {}).get('relations', []))}"
            )
            if parsed:
                print("  sample:", json.dumps(parsed, ensure_ascii=True)[:200])
        except Exception as exc:
            print(f"run={index + 1}: FAIL {type(exc).__name__} {str(exc)[:200]}")


if __name__ == "__main__":
    main()
