import csv
import json
import re
import statistics
from collections import Counter

IN_PATH = "data/fieldbook_1_ocr.jsonl"
CHECKLIST_PATH = "data/checklist.csv"
OUT_PATH = "data/fieldbook_1_chunks.jsonl"

LOW_TEXT = 300  # pages with less OCR text than this are illustration plates
MIN_CHARS = 80  # drop family/general chunks shorter than this

WORD = r"[A-Z][A-Za-z'’]*(?:-[A-Za-z]+)*"
HEADER_RE = re.compile(
    rf"^(?P<eng>{WORD}(?: {WORD}){{0,5}}) "
    rf"(?P<sci>[A-Z][a-z]{{2,}} (?:\([a-z]+\) )?[a-z]{{3,}})\b(?P<rest>.{{0,40}})$"
)
FAMILY_RE = re.compile(r"^(?P<name>[A-Z][A-Z ,'’\-–/&]+?)\s*(?P<fam>[A-Z][a-z]+(?:idae|inae))\s*$")
PLATE_RE = re.compile(r"^P[LI1]ATE\s*[0-9OIlSB]+")
SIZE_RE = re.compile(r"\d+\s?(?:[–-]\s?\d+)?\s?cm")
ID_RE = re.compile(r"\b[Il1]D\b")
DROP_LINES = {"SPECIES", "LIST", "SPECIES LIST"}
LABELS = {"Voice"}  # section labels inside accounts (HH, TN, TH, ID are caught as all-caps words)


def parse_header(text):
    m = HEADER_RE.match(text)
    if not m:
        return None
    first = m["eng"].split()[0]
    if first in LABELS or re.fullmatch(r"[A-Z]{2,}", first):
        return None  # e.g. "HH Dense scrub" is a habitat line, not a species
    return m


# ---- load OCR pages, skipping plates ----
pages = []
with open(IN_PATH, encoding="utf-8") as f:
    for raw in f:
        rec = json.loads(raw)
        if len(rec["text"].strip()) >= LOW_TEXT:
            pages.append(rec)
pages.sort(key=lambda r: r["page"])

# ---- clean lines ----
lines = []
for rec in pages:
    for l in rec["text"].splitlines():
        l = re.sub(r"[|¦]", " ", l)
        l = re.sub(r"\s+", " ", l).strip()
        if not l or l in DROP_LINES or re.fullmatch(r"\d{1,3}", l):
            continue
        letters = sum(c.isalpha() for c in l)
        if letters < 3 or letters / len(l.replace(" ", "")) < 0.5:
            continue  # OCR noise from maps and drawings
        lines.append((rec["page"], l))

# Layout of the book:
#   before the first plate title  -> introduction and family summaries
#   first plate .. last plate     -> species accounts
#   after the last plate          -> appendix of rarer species (headers with a size like "38-40 cm"),
#                                    then back matter (addresses, credits) which is dropped
plate_pages = {page for page, text in lines if PLATE_RE.match(text)}
first_plate, last_plate = min(plate_pages), max(plate_pages)

appendix_pages = set()
for page, text in lines:
    if page > last_plate:
        m = parse_header(text)
        if m and SIZE_RE.search(m["rest"]):
            appendix_pages.add(page)
appendix_last = max(appendix_pages) if appendix_pages else last_plate
dropped_pages = [rec["page"] for rec in pages if rec["page"] > appendix_last]

chunks = []


def join_lines(parts):
    out = ""
    for p in parts:
        if not out:
            out = p
        elif out.endswith("-"):
            out += p  # line broke inside a hyphenated word
        else:
            out += " " + p
    return out


def finish(chunk):
    if chunk is None:
        return
    body = chunk.pop("lines")
    if chunk["type"] in ("species", "family"):
        text = body[0] + "\n" + join_lines(body[1:])
    else:
        text = join_lines(body)
    text = text.strip()
    if chunk["type"] in ("family", "general") and len(text) < MIN_CHARS:
        return
    chunk["text"] = text
    chunks.append(chunk)


current = None
plate = None
skip = False  # True right after a PLATE title, until the first species header (drops map labels)

for page, text in lines:
    if page > appendix_last:
        continue  # back matter
    in_plates = first_plate <= page <= last_plate
    in_appendix = page > last_plate

    if in_plates and PLATE_RE.match(text):
        finish(current)
        current = None
        plate = re.sub(r"\s+[a-z]{1,3}$", "", text)
        skip = True
        continue

    if in_plates or in_appendix:
        m = parse_header(text)
        if m and (in_plates or SIZE_RE.search(m["rest"])):
            finish(current)
            size = SIZE_RE.search(m["rest"])
            header = f"{m['eng']} {m['sci']}" + (f" {size.group(0)}" if size else "")
            current = {"type": "species", "section": "appendix" if in_appendix else "main",
                       "english_name": m["eng"],
                       "scientific_name": re.sub(r"\s*\([a-z]+\)", "", m["sci"]),
                       "plate": None if in_appendix else plate,
                       "page_start": page, "page_end": page, "lines": [header]}
            skip = False
            continue
        if skip:
            continue
        if in_appendix and current is None:
            continue
    else:
        fm = FAMILY_RE.match(text)
        if fm:
            finish(current)
            current = {"type": "family", "family": fm["fam"],
                       "page_start": page, "page_end": page, "lines": [text]}
            continue

    if current is None or (current["type"] == "general" and current["page_start"] != page):
        finish(current)
        current = {"type": "general", "page_start": page, "page_end": page, "lines": []}
    current["lines"].append(text)
    current["page_end"] = page

finish(current)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    for ch in chunks:
        f.write(json.dumps(ch, ensure_ascii=False) + "\n")

# ---- diagnostics ----
species = [c for c in chunks if c["type"] == "species"]
main = [c for c in species if c["section"] == "main"]
appendix = [c for c in species if c["section"] == "appendix"]
print("Chunks by type:", dict(Counter(c["type"] for c in chunks)))
print(f"Species: {len(main)} in plates (pages {first_plate}-{last_plate}), {len(appendix)} in appendix (pages {last_plate + 1}-{appendix_last})")
print(f"Back-matter text pages dropped: {len(dropped_pages)}", dropped_pages[:3], "...", dropped_pages[-1:])
if species:
    lens = sorted(len(c["text"]) for c in species)
    print(f"Species chunk length: min {lens[0]}, median {statistics.median(lens):.0f}, max {lens[-1]}")

short = [c for c in species if len(c["text"]) < 150]
print(f"\nVery short species chunks (<150 chars): {len(short)}")
for c in short[:10]:
    print(f"  p{c['page_start']}: {c['text'][:90]!r}")

no_id = [c for c in main if not ID_RE.search(c["text"])]
print(f"\nPlate species without an 'ID' section: {len(no_id)} (rare visitors often have short accounts)")

print("\nLongest species chunks:")
for c in sorted(species, key=lambda c: len(c["text"]), reverse=True)[:4]:
    print(f"  p{c['page_start']}-{c['page_end']} len {len(c['text'])}: {c['text'][:70]!r}")

with open(CHECKLIST_PATH, encoding="utf-8") as f:
    checklist = list(csv.DictReader(f))
sci_in_book = {c["scientific_name"].lower() for c in species}
eng_in_book = {c["english_name"].lower() for c in species}
covered = [r for r in checklist
           if r["scientific_name"].lower() in sci_in_book or r["english_name"].lower() in eng_in_book]
print(f"\nChecklist species found in fieldbook_1 by exact name: {len(covered)} of {len(checklist)}")