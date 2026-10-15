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

INDUCTION_TEXT = (
    "本指引所称金融产品，是指面向投资者发行的理财产品、基金与保险产品。"
    "金融机构销售金融产品时应当向投资者充分揭示风险。"
    "金融机构应当遵守相关法规与合规要求，防范金融风险。"
)

EXTRACT_PROMPT = (
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

INDUCTION_PROMPT = (
    "你是一名本体工程师。请阅读给定文本，归纳其中反复出现的领域概念与概念间的关系。\n\n"
    "要求：\n"
    "1. 只输出一个 JSON 对象，格式为 "
    '{"classes":[{"local_name":"英文名","label":"中文标签","definition":"一句话定义","aliases":["别名"]}],'
    '"object_properties":[{"local_name":"英文名","label":"中文标签","definition":"一句话定义",'
    '"domain":"域类中文标签","range":"值域类中文标签"}]}；\n'
    "2. local_name 必须是合法的英文标识符；\n"
    "3. label 与 definition 必填，definition 用一句话概括该概念；\n"
    "4. object_properties 的 domain 与 range 必须引用 classes 中的中文标签；\n"
    "5. 只归纳文本中确实出现、且具有领域通用性的概念；\n"
    "6. 最多输出 6 个类与 4 个对象属性，只保留最核心、出现频率最高的概念；\n"
    '7. 没有可归纳内容时输出 {"classes":[],"object_properties":[]}。\n\n'
    "文本：\n" + INDUCTION_TEXT
)


async def call_once(prompt: str, timeout: float = 60.0) -> tuple[str, float, int]:
    client = AsyncOpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], base_url=BASE, timeout=timeout)
    start = time.time()
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "你只输出 JSON，不输出任何其他内容。"},
                {"role": "user", "content": prompt},
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
    print("--- extract probe ---")
    for index in range(2):
        try:
            raw, elapsed, tokens = asyncio.run(call_once(EXTRACT_PROMPT))
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else None
            print(
                f"run={index + 1}: ok elapsed={elapsed:.1f}s tokens={tokens} "
                f"json_valid={parsed is not None} entities={len((parsed or {}).get('entities', []))} "
                f"relations={len((parsed or {}).get('relations', []))}"
            )
        except Exception as exc:
            print(f"run={index + 1}: FAIL {type(exc).__name__} {str(exc)[:160]}")
    print("--- induction probe ---")
    for index in range(3):
        try:
            raw, elapsed, tokens = asyncio.run(call_once(INDUCTION_PROMPT, timeout=180.0))
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = json.loads(match.group(0)) if match else None
            classes = (parsed or {}).get("classes", [])
            props = (parsed or {}).get("object_properties", [])
            print(
                f"run={index + 1}: ok elapsed={elapsed:.1f}s tokens={tokens} "
                f"json_valid={parsed is not None} classes={len(classes)} props={len(props)}"
            )
            if parsed:
                print("  sample:", json.dumps(parsed, ensure_ascii=True)[:300])
        except Exception as exc:
            print(f"run={index + 1}: FAIL {type(exc).__name__} {str(exc)[:160]}")


if __name__ == "__main__":
    main()
