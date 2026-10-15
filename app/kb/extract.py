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


def build_induction_prompt(text: str) -> str:
    return (
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
        "文本：\n" + text
    )


LOCAL_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def parse_induction(raw: str, text: str) -> dict:
    data = json.loads(raw)
    classes = []
    object_properties = []
    discarded = 0
    for item in data.get("classes", []):
        local_name = str(item.get("local_name", ""))
        label = str(item.get("label", ""))
        definition = str(item.get("definition", ""))
        if LOCAL_NAME_RE.match(local_name) and label and label in text and definition:
            classes.append(
                {
                    "local_name": local_name,
                    "label": label,
                    "definition": definition,
                    "aliases": [str(a) for a in item.get("aliases", []) if str(a)],
                }
            )
        else:
            discarded += 1
    labels = {c["label"] for c in classes}
    for item in data.get("object_properties", []):
        local_name = str(item.get("local_name", ""))
        label = str(item.get("label", ""))
        definition = str(item.get("definition", ""))
        domain = str(item.get("domain", ""))
        range_label = str(item.get("range", ""))
        if (
            LOCAL_NAME_RE.match(local_name)
            and label
            and definition
            and domain in labels
            and range_label in labels
        ):
            object_properties.append(
                {
                    "local_name": local_name,
                    "label": label,
                    "definition": definition,
                    "domain": domain,
                    "range": range_label,
                }
            )
        else:
            discarded += 1
    return {"classes": classes, "object_properties": object_properties, "discarded": discarded}


async def induct_chunk(settings: Settings, text: str) -> tuple[dict, int]:
    client = AsyncOpenAI(api_key=settings.dashscope_api_key, base_url=BASE_URL, timeout=180.0)
    try:
        resp = await client.chat.completions.create(
            model=settings.kb_extract_model,
            messages=[
                {"role": "system", "content": "你只输出 JSON，不输出任何其他内容。"},
                {"role": "user", "content": build_induction_prompt(text)},
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
        raise EmbedError(EmbedErrorCode.INPUT, "归纳响应不含 JSON")
    try:
        parsed = parse_induction(match.group(0), text)
    except json.JSONDecodeError as exc:
        raise EmbedError(EmbedErrorCode.INPUT, f"归纳响应 JSON 非法: {exc}") from exc
    tokens = resp.usage.total_tokens if resp.usage else 0
    return parsed, tokens


async def induct_chunk_with_retry(
    settings: Settings, text: str
) -> tuple[dict, int, int]:
    retries = 0
    for delay in RETRY_DELAY_SECONDS + (None,):
        try:
            parsed, tokens = await induct_chunk(settings, text)
            return parsed, tokens, retries
        except EmbedError as exc:
            retryable = exc.code in (EmbedErrorCode.RATE, EmbedErrorCode.UPSTREAM)
            if not retryable or delay is None:
                raise
            retries += 1
            await asyncio.sleep(delay)
    raise EmbedError(EmbedErrorCode.UPSTREAM, "重试次数耗尽")
