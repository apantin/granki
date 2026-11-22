"""Сводка дневника поездок для таблиц утверждений серии.

Запуск из корня проекта:
  python3 -I series/winter-bike/shared/scripts/summarize.py materials/bike/trips.csv series/winter-bike/shared/data/summary.csv

Строка сводки — ключ `key` (латиницей, для ID утверждений) и срез: `group` — резина (all, обычные, шипы), «дни» или «пропуск»; `sub` — покрытие (all — без фильтра) или причина пропуска.
Время (minutes_*) — только поездки по основному маршруту 23,6 км; объезды считаются отдельно (detours).
Дни без поездки — строки с distance_km = 0.
"""
import csv
import sys
from statistics import mean

src, out = sys.argv[1], sys.argv[2]
rows = list(csv.DictReader(open(src, encoding="utf-8")))
trips = [r for r in rows if float(r["distance_km"]) > 0]
skips = [r for r in rows if float(r["distance_km"]) == 0]

def r1(x):
    return f"{x:.1f}"

def stats(sel):
    base = [r for r in sel if r["distance_km"] == "23.6"]
    mins = [int(r["minutes"]) for r in base]
    temps = [int(r["temp_c"]) for r in sel]
    falls = sum(int(r["falls"]) for r in sel)
    skids = sum(int(r["skids"]) for r in sel)
    n = len(sel)
    return {
        "trips": n,
        "base_trips": len(base),
        "detours": n - len(base),
        "minutes_mean": r1(mean(mins)) if mins else "",
        "minutes_min": min(mins) if mins else "",
        "minutes_max": max(mins) if mins else "",
        "falls": falls,
        "skids": skids,
        "fall_days": sum(1 for r in sel if int(r["falls"]) > 0),
        "falls_per_10_trips": r1(10 * falls / n) if n else "",
        "skids_per_trip": r1(skids / n) if n else "",
        "temp_mean": r1(mean(temps)) if temps else "",
        "temp_min": min(temps) if temps else "",
        "temp_max": max(temps) if temps else "",
    }

surfaces = ["сухо", "мокро", "накат", "лёд", "свежий снег"]
tires = ["обычные", "шипы"]
SLUG = {"all": "all", "сухо": "dry", "мокро": "wet", "накат": "packed", "лёд": "ice",
        "свежий снег": "snow", "обычные": "reg", "шипы": "studs",
        "не поехал, метель/не чищено": "storm", "простыл": "sick"}
out_rows = []
for t in ["all"] + tires:
    for s in ["all"] + surfaces:
        sel = [r for r in trips if (t == "all" or r["tires"] == t) and (s == "all" or r["surface"] == s)]
        if sel:
            out_rows.append({"key": f"{SLUG[t]}-{SLUG[s]}", "group": t, "sub": s, "days": len(sel), **stats(sel)})

out_rows.append({"key": "days-all", "group": "дни", "sub": "all", "days": len(rows)})
out_rows.append({"key": "skip-all", "group": "пропуск", "sub": "all", "days": len(skips)})
for reason in sorted({r["note"] for r in skips}):
    out_rows.append({"key": f"skip-{SLUG[reason]}", "group": "пропуск", "sub": reason, "days": sum(1 for r in skips if r["note"] == reason)})

fields = ["key", "group", "sub", "days"] + list(stats(trips).keys())
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(out_rows)
