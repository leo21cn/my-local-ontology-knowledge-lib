import sqlite3

con = sqlite3.connect(r"D:\szp\work\multi-agents-brainstorming\program\data\sparkwave.db")
cur = con.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("tables:", [r[0] for r in cur.fetchall()])
if any(True for _ in []):
    pass
for t in ("rooms", "Room"):
    try:
        cur.execute(f"SELECT * FROM {t} LIMIT 5")
        rows = cur.fetchall()
        print(t, "rows:", len(rows))
        for r in rows:
            print("  ", r)
    except Exception as e:
        print(t, "ERR", e)
