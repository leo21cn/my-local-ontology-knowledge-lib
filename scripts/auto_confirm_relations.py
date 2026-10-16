from collections import Counter, defaultdict

from kb.config import get_settings
from kb.neo4j_store import get_driver
from kb.proposals import list_pending, resolve_pending


def main() -> None:
    driver = get_driver(get_settings())
    items = [i for i in list_pending(driver, limit=5000)
             if i["kind"] == "relation_proposal" and i["status"] == "open"]
    confirmed = 0
    remaining: Counter = Counter()
    for item in items:
        result = resolve_pending(driver, item["pid"], "confirm")
        if result["status"] == "confirmed":
            confirmed += 1
        else:
            reason = result.get("error", "unknown")
            if len(reason) > 60:
                reason = reason[:60]
            remaining[reason] += 1
    print("confirmed relations:", confirmed, "of", len(items))
    if remaining:
        print("remaining open:")
        for reason, count in remaining.most_common():
            print(f"  [{count}] {reason}")
    driver.close()


if __name__ == "__main__":
    main()
