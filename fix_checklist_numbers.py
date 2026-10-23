import csv
from collections import Counter

PATH = "data/checklist.csv"

with open(PATH, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

seen = Counter()
changed = []
for r in rows:
    original = r["no"]
    seen[original] += 1
    if seen[original] > 1:
        r["no"] = original + "b" * (seen[original] - 1)
        changed.append((original, r["no"], r["english_name"], r["scientific_name"]))

with open(PATH, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Rows: {len(rows)}   renumbered: {len(changed)}")
for original, new, eng, sci in changed:
    print(f"  {original} -> {new}: {eng} | {sci}")
print("Distinct numbers now:", len({r['no'] for r in rows}))