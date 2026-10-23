import csv
import json
import re
import statistics
from collections import Counter

IN_PATH = "data/fieldbook_2_pages.jsonl"
CHECKLIST_PATH = "data/checklist.csv"
OUT_PATH = "data/fieldbook_2_chunks.jsonl"

# size line, e.g. "17 cm", "14cm", "56–66 cm", "180–230 cm,  90–100 cm" (with invisible sex symbols in front)
SIZE_RE = re.compile(r"^\W*(c\.\s*)?\d[\d.,–\- ]*cm\b")
FAMILY_RE = re.compile(r"^[A-Z][A-Z ,'’\-–/&]+ [A-Z][a-z]+(?:idae|inae)$")
# English name + scientific name, allowing a bracketed epithet: "Milvus (migrans) lineatus"
HEADER_RE = re.compile(r"^(?P<eng>.+?)\s+(?P<sci>[A-Z][a-z]+ (?:\([a-z]+\) )?[a-z]+)$")
APPENDIX_RE = re.compile(r"^APPENDIX\b")
MIN_FAMILY_CHARS = 80
PAGE_TYPES = ("general", "appendix")

# ---- load checklist (used to attach order/family/status to each species) ----
with open(CHECKLIST_PATH, encoding="utf-8") as f:
    checklist = list(csv.DictReader(f))
by_sci = {r["scientific_name"].lower(): r for r in checklist}
by_eng = {r["english_name"].lower(): r for r in checklist}

# ---- flatten all pages into (page, line) pairs ----
lines = []
with open(IN_PATH, encoding="utf-8") as f:
    for raw in f:
        rec = json.loads(raw)
        page_lines = [l.strip() for l in rec["text"].splitlines() if l.strip()]
        if page_lines and page_lines[0].isdigit():  # printed page number
            page_lines = page_lines[1:]
        if page_lines and page_lines[-1].isdigit():
            page_lines = page_lines[:-1]
        for l in page_lines:
            lines.append((rec["page"], l))

chunks = []
unrecognized = []


def finish(chunk):
    if chunk is None:
        return
    body = chunk["lines"]
    if chunk["type"] in ("species", "family"):
        text = body[0] + "\n" + " ".join(body[1:])
    else:
        text = " ".join(body)
    text = text.strip()
    if chunk["type"] == "family" and len(text) < MIN_FAMILY_CHARS:
        return  # heading with no summary text
    chunk["text"] = text
    del chunk["lines"]
    chunks.append(chunk)


current = None
section = "main"      # main -> appendix -> index
seen_species = False

for i, (page, text) in enumerate(lines):
    if section == "index":
        continue  # the index is just names and page numbers, not useful for answering

    nxt = lines[i + 1][1] if i + 1 < len(lines) else ""

    # start of appendices / index (only after species accounts began, so the contents page is ignored)
    if seen_species and section == "main" and APPENDIX_RE.match(text):
        finish(current)
        section = "appendix"
        current = {"type": "appendix", "page_start": page, "page_end": page, "lines": [text]}
        continue
    if section == "appendix" and text == "INDEX":
        finish(current)
        current = None
        section = "index"
        continue

    if FAMILY_RE.match(text):
        finish(current)
        current = {"type": "family", "family": text.split()[-1],
                   "page_start": page, "page_end": page, "lines": [text]}
        continue

    if SIZE_RE.match(nxt) and not SIZE_RE.match(text):
        m = HEADER_RE.match(text)
        if m:
            finish(current)
            sci_book = m["sci"]
            sci_clean = re.sub(r"\s*\([a-z]+\)", "", sci_book)
            current = {"type": "species", "section": section,
                       "english_name": m["eng"],
                       "scientific_name": sci_clean,
                       "scientific_name_book": sci_book,
                       "page_start": page, "page_end": page, "lines": [text]}
            seen_species = True
            continue
        unrecognized.append((page, text))

    if current is None or (current["type"] in PAGE_TYPES and current["page_start"] != page):
        finish(current)
        kind = "appendix" if section == "appendix" else "general"
        current = {"type": kind, "page_start": page, "page_end": page, "lines": []}
    current["lines"].append(text)
    current["page_end"] = page

finish(current)

# ---- attach checklist info to species chunks ----
for ch in chunks:
    if ch["type"] != "species":
        continue
    row = by_sci.get(ch["scientific_name"].lower()) or by_eng.get(ch["english_name"].lower())
    ch["in_checklist"] = row is not None
    if row:
        ch.update({"checklist_no": row["no"], "order": row["order"],
                   "family": row["family"], "gts": row["gts"],
                   "nts": row["nts"], "cites": row["cites"]})

with open(OUT_PATH, "w", encoding="utf-8") as f:
    for ch in chunks:
        f.write(json.dumps(ch, ensure_ascii=False) + "\n")

# ---- diagnostics ----
species = [c for c in chunks if c["type"] == "species"]
print("Chunks by type:", dict(Counter(c["type"] for c in chunks)))
matched = [c for c in species if c["in_checklist"]]
print(f"Species accounts: {len(species)}   matched to checklist: {len(matched)}")
print(f"Size lines with no recognised header: {len(unrecognized)}")
for p, t in unrecognized[:10]:
    print("  ", p, t)

if species:
    lens = sorted(len(c["text"]) for c in species)
    print(f"Species chunk length: min {lens[0]}, median {statistics.median(lens):.0f}, max {lens[-1]}")

print("\nLongest chunks:")
for c in sorted(chunks, key=lambda c: len(c["text"]), reverse=True)[:5]:
    print(f"  {c['type']} p{c['page_start']}-{c['page_end']} len {len(c['text'])}: {c['text'][:70]!r}")

unmatched = [c for c in species if not c["in_checklist"]]
print(f"\n=== A. Fieldbook accounts NOT in checklist: {len(unmatched)} ===")
for c in unmatched:
    print(f"{c['english_name']} | {c['scientific_name']} | p{c['page_start']} | {c['section']}")

found = {c["checklist_no"] for c in matched}
not_found = [r for r in checklist if r["no"] not in found]
print(f"\n=== B. Checklist species with NO fieldbook account: {len(not_found)} ===")
for r in not_found:
    print(f"{r['no']} {r['english_name']} | {r['scientific_name']}")