import hashlib
import re
from dataclasses import dataclass

import frontmatter

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class ChunkDraft:
    heading_path: list[str]
    text: str


def chunk_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_frontmatter(text: str) -> tuple[dict, str]:
    try:
        post = frontmatter.loads(text)
    except Exception:
        return {}, text
    return dict(post.metadata), post.content


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 2 <= max_chars:
            buffer = f"{buffer}\n\n{paragraph}".strip()
            continue
        if buffer:
            parts.append(buffer)
        while len(paragraph) > max_chars:
            parts.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars - overlap:]
        buffer = paragraph
    if buffer:
        parts.append(buffer)
    return parts


def chunk_markdown(body: str, max_chars: int = 700, overlap: int = 60) -> list[ChunkDraft]:
    matches = list(HEADING_RE.finditer(body))
    if not matches:
        return [
            ChunkDraft(heading_path=[], text=part)
            for part in _split_long(body.strip(), max_chars, overlap)
            if part.strip()
        ]
    drafts: list[ChunkDraft] = []
    stack: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        level = len(match.group(1))
        title = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        content = body[match.end():end].strip()
        if not content:
            continue
        for part in _split_long(content, max_chars, overlap):
            if part.strip():
                drafts.append(ChunkDraft(heading_path=[t for _, t in stack], text=part))
    return drafts
