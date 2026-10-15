import asyncio
import json
import re

from openai import AsyncOpenAI

from kb.config import Settings
from kb.embed import BASE_URL, EmbedError, EmbedErrorCode, classify_error

RETRY_DELAY_SECONDS = (2, 4)


def build_signature(ontology: dict) -> dict:
    return {
        "classes": [
            {
                "iri": c["iri"],
                "label": c.get("label_zh", ""),
                "aliases": c.get("aliases", []),
                "definition": c.get("definition", ""),
            }
            for c in ontology.get("classes", [])
        ],
        "object_properties": [
            {
                "iri": p["iri"],
                "label": p.get("label_zh", ""),
                "domain": p.get("domain_iri", ""),
                "range": p.get("range_iri", ""),
            }
            for p in ontology.get("object_properties", [])
        ],
    }


def build_prompt(signature: dict, text: str) -> str:
    return (
        "你是知识图谱抽取助手。根据给定的本体签名，从文本中抽取实体与关系。\n\n"
        "本体签名（JSON）：\n"
        + json.dumps(signature, ensure_ascii=False)
        + "\n\n要求：\n"
        "1. 只输出一个 JSON 对象，格式为 "
        '{"entities":[{"term":"...","class_iri":"..."}],'
        '"relations":[{"from":"...","to":"...","type_iri":"..."}]}；\n'
        "2. term/from/to 必须是文本中逐字出现的名称片段；\n"
        "3. class_iri 与 type_iri 只能取本体签名中列出的 IRI；\n"
        '4. 没有可抽取内容时输出 {"entities":[],"relations":[]}。\n\n'
        "文本：\n" + text
    )


def parse_extraction(raw: str, text: str, signature: dict) -> dict:
    data = json.loads(raw)
    class_iris = {c["iri"] for c in signature["classes"]}
    prop_iris = {p["iri"] for p in signature["object_properties"]}
    entities = []
    relations = []
    discarded = 0
    for item in data.get("entities", []):
        term = str(item.get("term", ""))
        if term and term in text and item.get("class_iri") in class_iris:
            entities.append({"term": term, "class_iri": item["class_iri"]})
        else:
            discarded += 1
    for item in data.get("relations", []):
        from_term = str(item.get("from", ""))
        to_term = str(item.get("to", ""))
        if (
            from_term
            and to_term
            and from_term in text
            and to_term in text
            and item.get("type_iri") in prop_iris
        ):
            relations.append({"from": from_term, "to": to_term, "type_iri": item["type_iri"]})
        else:
            discarded += 1
    return {"entities": entities, "relations": relations, "discarded": discarded}


async def extract_chunk(settings: Settings, text: str, signature: dict) -> tuple[dict, int]:
    client = AsyncOpenAI(api_key=settings.dashscope_api_key, base_url=BASE_URL, timeout=60.0)
    try:
        resp = await client.chat.completions.create(
            model=settings.kb_extract_model,
            messages=[
                {"role": "system", "content": "你只输出 JSON，不输出任何其他内容。"},
                {"role": "user", "content": build_prompt(signature, text)},
            ],
            temperature=0,
        )
    except Exception as exc:
        raise EmbedError(classify_error(exc), str(exc)) from exc
    finally:
        await client.close()
    raw = resp.choices[0].message.content or ""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        raise EmbedError(EmbedErrorCode.INPUT, "抽取响应不含 JSON")
    try:
        parsed = parse_extraction(match.group(0), text, signature)
    except json.JSONDecodeError as exc:
        raise EmbedError(EmbedErrorCode.INPUT, f"抽取响应 JSON 非法: {exc}") from exc
    tokens = resp.usage.total_tokens if resp.usage else 0
    return parsed, tokens


async def extract_chunk_with_retry(
    settings: Settings, text: str, signature: dict
) -> tuple[dict, int, int]:
    retries = 0
    for delay in RETRY_DELAY_SECONDS + (None,):
        try:
            parsed, tokens = await extract_chunk(settings, text, signature)
            return parsed, tokens, retries
        except EmbedError as exc:
            retryable = exc.code in (EmbedErrorCode.RATE, EmbedErrorCode.UPSTREAM)
            if not retryable or delay is None:
                raise
            retries += 1
            await asyncio.sleep(delay)
    raise EmbedError(EmbedErrorCode.UPSTREAM, "重试次数耗尽")
