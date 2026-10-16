from collections import defaultdict

from kb.config import get_settings
from kb.neo4j_store import get_driver
from kb.proposals import list_pending, resolve_pending


def main() -> None:
    driver = get_driver(get_settings())
    items = [i for i in list_pending(driver, limit=5000)
             if i["kind"] == "proposal" and i["status"] == "open"]
    by_corpus = defaultdict(list)
    for item in items:
        by_corpus[item["corpus_id"]].append(item)

    total = 0
    for corpus_id, corpus_items in sorted(by_corpus.items()):
        confirmed = 0
        for item in corpus_items:
            result = resolve_pending(driver, item["pid"], "confirm")
            if result["status"] == "confirmed":
                confirmed += 1
        print(f"corpus {corpus_id}: confirmed {confirmed} of {len(corpus_items)}")
        total += confirmed
    print("total confirmed:", total)
    driver.close()


if __name__ == "__main__":
    main()
