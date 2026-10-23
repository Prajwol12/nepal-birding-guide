import csv
import re
import pdfplumber

MISSING = ["685", "844", "855", "872"]

print("Raw lines for missing numbers:")
with pdfplumber.open("data/checklist.pdf") as pdf:
    for page_num, page in enumerate(pdf.pages, start=1):
        for line in (page.extract_text() or "").splitlines():
            if line.split(" ")[0] in MISSING:
                print(page_num, line)

with open("data/checklist.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

bad = [r for r in rows if re.search(r"f[il]\s", r["english_name"] + " " + r["scientific_name"])]
print(f"\nNames with a possible fi/fl split: {len(bad)}")
for r in bad[:10]:
    print(r["no"], r["english_name"], "|", r["scientific_name"])

print("\nDistinct GTS values:", sorted({r["gts"] for r in rows}))
print("Distinct NTS values:", sorted({r["nts"] for r in rows}))
print("Distinct CITES values:", sorted({r["cites"] for r in rows}))
print("Rows missing order or family:", sum(1 for r in rows if not r["order"] or not r["family"]))