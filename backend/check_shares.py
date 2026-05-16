from history_db import HistoryDB

hdb = HistoryDB()
data = hdb.get_shares_by_code('160644', days=7)

print("基金 160644 的份额数据：")
for d in data[:3]:
    print(f"日期: {d['date']}, 份额: {d['shares']}")

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
        incr = s1 - s2
        print(f"\n最新日期: {latest['date']}, 份额: {s1}")
        print(f"上个日期: {previous['date']}, 份额: {s2}")
        print(f"增量: {incr} 份")
        print(f"增量（万份）: {incr / 10000:.2f} 万份")
