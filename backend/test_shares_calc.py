from config import Config
from history_db import get_history_db

hdb = get_history_db()
data = hdb.get_shares_by_code('160644', days=7)

print("查询结果:")
for d in data:
    print(f"  {d['date']}: {d['shares']} (type={type(d['shares'])})")

print(f"\n总数: {len(data)}")

if len(data) >= 2:
    latest = data[0]
    previous = None
    for record in data[1:]:
        if record['date'] != latest['date']:
            previous = record
            break
    
    if previous:
        s1 = float(latest['shares'])
        s2 = float(previous['shares'])
        incr = round(s1 - s2, 2)
        print(f"\n计算结果:")
        print(f"  Latest ({latest['date']}): {s1}")
        print(f"  Previous ({previous['date']}): {s2}")
        print(f"  Increment: {incr}")
    else:
        print("\n未找到不同日期的记录")
