import csv
import re
import pdfplumber

PDF_PATH = "data/checklist.pdf"
OUT_CSV = "data/checklist.csv"
TOL = 8  # tolerance in PDF points for column boundaries


def clean(text):
    # fix "fi"/"fl" ligature gaps: "rufi na" -> "rufina", "fl avicollis" -> "flavicollis"
    return re.sub(r"([Ff][il])\s+(?=[a-z])", r"\1", text)


def find_columns(words):
    """Column start positions from the header row; None if this page has no header."""
    starts = {}
    for w in words:
        t = w["text"]
        if t == "English":
            starts.setdefault("english", w["x0"])
        elif t.startswith("Scientif"):
            starts.setdefault("scientific", w["x0"])
        elif t == "Nepali":
            starts.setdefault("nepali", w["x0"])
        elif t == "GTS":
            starts.setdefault("gts", w["x0"])
        elif t == "NTS":
            starts.setdefault("nts", w["x0"])
        elif t == "CITES":
            starts.setdefault("cites", w["x0"])
    return starts if len(starts) == 6 else None


def column_of(x0, c):
    if x0 < c["english"] - 2:
        return "no"
    if x0 < c["scientific"] - TOL:
        return "english"
    if x0 < c["nepali"] - TOL:
        return "scientific"
    if x0 < c["gts"] - TOL:
        return "nepali"
    if x0 < c["nts"] - TOL:
        return "gts"
    if x0 < c["cites"] - TOL:
        return "nts"
    return "cites"


def group_lines(words, tol=3):
    lines = []
    for w in sorted(words, key=lambda w: ((w["top"] + w["bottom"]) / 2, w["x0"])):
        y = (w["top"] + w["bottom"]) / 2
        if lines and abs(lines[-1]["y"] - y) <= tol:
            lines[-1]["words"].append(w)
        else:
            lines.append({"y": y, "words": [w]})
    return lines


rows, warnings = [], []
order = family = None
cols = None

with pdfplumber.open(PDF_PATH) as pdf:
    for page_num, page in enumerate(pdf.pages, start=1):
        words = page.extract_words()
        cols = find_columns(words) or cols
        if cols is None:
            continue  # intro pages before the first table

        # drop the garbled Nepali column before grouping into lines
        words = [w for w in words if column_of(w["x0"], cols) != "nepali"]

        for line in group_lines(words):
            cells = {k: [] for k in ["no", "english", "scientific", "gts", "nts", "cites"]}
            for w in sorted(line["words"], key=lambda w: w["x0"]):
                cells[column_of(w["x0"], cols)].append(w["text"])
            c = {k: " ".join(v).strip() for k, v in cells.items()}
            c["english"] = clean(c["english"])
            c["scientific"] = clean(c["scientific"])

            if not re.search("[A-Za-z]", c["english"] + c["scientific"]):
                continue  # page numbers, blank lines
            if not c["no"] and c["english"].startswith("English"):
                continue  # repeated header row

            if re.fullmatch(r"\d+[a-z]?", c["no"]) and c["english"]:
                rows.append({
                    "no": c["no"],
                    "english_name": c["english"],
                    "scientific_name": c["scientific"],
                    "order": order,
                    "family": family,
                    "gts": c["gts"],
                    "nts": c["nts"],
                    "cites": c["cites"],
                })
            elif c["english"] and not c["scientific"]:
                if c["english"].isupper():
                    order = c["english"].title()
                elif len(c["english"].split()) == 1:
                    family = c["english"]
                else:
                    warnings.append((page_num, c))
            else:
                warnings.append((page_num, c))

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

print(f"Rows parsed: {len(rows)}")
nums = sorted({int(r["no"]) for r in rows if r["no"].isdigit()})
print(f"Species numbers: {nums[0]} to {nums[-1]}")
missing = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
print(f"Missing numbers: {missing[:30]}")

table_warnings = [(p, c) for p, c in warnings if p < 35]
print(f"Warnings on table pages: {len(table_warnings)}")
for p, c in table_warnings[:25]:
    print(p, c)