"""生成 200 篇验收语料到 knowledge-lib-base-folder/acceptance/。

每篇含：唯一可检索表述、两个标签、至少一个本体类别名，
其中三篇共享同一别名以支撑 V8 的多锚点判据。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "knowledge-lib-base-folder" / "acceptance"
TOTAL = 200
SHARED_ALIAS = "验收项目组"
SHARED_INDEXES = (3, 47, 121)


def note(index: int) -> str:
    tags = ["验收", "批次一" if index % 2 == 0 else "批次二"]
    alias = SHARED_ALIAS if index in SHARED_INDEXES else f"专题{index:03d}"
    return f"""---
tags: {tags}
---

# 验收笔记 {index:03d}

## 概述

唯一表述标识符 ACCEPT-{index:04d}-UNIQUE 出现在本节，用于检索命中判定。

## 关联

本节涉及{alias}，其职责范围与交付边界在本篇内描述。

## 结论

第 {index} 篇的结论段落，供上下文回读校验。
"""


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for index in range(1, TOTAL + 1):
        (ROOT / f"note-{index:03d}.md").write_text(note(index), encoding="utf-8")
    print(f"已生成 {TOTAL} 篇到 {ROOT}")


if __name__ == "__main__":
    main()
