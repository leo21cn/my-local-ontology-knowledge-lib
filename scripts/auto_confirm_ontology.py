from collections import defaultdict

from kb.config import get_settings
from kb.neo4j_store import get_driver
from kb.proposals import list_pending, resolve_pending

MAX_PASSES = 6

ORDER = {"class": 0, "object_property": 1, "datatype_property": 2}


def main() -> None:
    settings = get_settings()
    driver = get_driver(settings)
    items = list_pending(driver, limit=5000)
    by_corpus = defaultdict(list)
    for item in items:
        if item["kind"] == "ontology_proposal" and item["status"] == "open":
            by_corpus[item["corpus_id"]].append(item)

    print(f"open ontology proposals: {sum(len(v) for v in by_corpus.values())} "
          f"across corpora {list(by_corpus.keys())}")

    for corpus_id, corpus_items in sorted(by_corpus.items()):
        confirmed = 0
        duplicates = 0
        remaining: dict[str, list[dict]] = {}
        for _ in range(MAX_PASSES):
            progress = 0
            for item in sorted(corpus_items, key=lambda i: ORDER.get(i["payload"].get("element_kind"), 9)):
                if item["status"] != "open":
                    continue
                result = resolve_pending(driver, item["pid"], "confirm")
                if result["status"] == "confirmed":
                    item["status"] = "confirmed"
                    confirmed += 1
                    progress += 1
                elif result["status"] == "rejected":
                    item["status"] = "rejected"
                    duplicates += 1
                    progress += 1
                else:
                    reason = result.get("error", "unknown")
                    remaining.setdefault(reason, []).append(item)
            if progress == 0:
                break
        print(f"\ncorpus {corpus_id}: confirmed={confirmed} duplicate_closed={duplicates} "
              f"remaining_open={len(remaining)}")
        for reason, entries in remaining.items():
            print(f"  [{len(entries)}] {reason[:160]}")

    driver.close()


if __name__ == "__main__":
    main()
