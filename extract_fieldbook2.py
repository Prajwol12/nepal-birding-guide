import json
import unicodedata

import fitz  # PyMuPDF

PDF_PATH = "data/fieldbook_2.pdf"
OUT_PATH = "data/fieldbook_2_pages.jsonl"
MIN_CHARS = 300  # pages with less text than this are treated as plates

doc = fitz.open(PDF_PATH)
kept, dropped = [], []

for i, page in enumerate(doc, start=1):
    text = page.get_text("text")
    text = unicodedata.normalize("NFKC", text)  # turns ligatures like "ﬁ" into "fi"
    text = text.replace("\u00ad", "")  # soft hyphens
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(text) < MIN_CHARS:
        dropped.append((i, len(text)))
    else:
        kept.append({"page": i, "text": text})

with open(OUT_PATH, "w", encoding="utf-8") as f:
    for rec in kept:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

print(f"Total pages: {len(doc)}")
print(f"Kept: {len(kept)}   Dropped (little text): {len(dropped)}")
print("Dropped pages (first 40):", [p for p, _ in dropped[:40]])
print(f"Total characters kept: {sum(len(r['text']) for r in kept)}")

for idx in [len(kept) // 5, len(kept) // 2, (len(kept) * 4) // 5]:
    rec = kept[idx]
    print("=" * 60)
    print(f"PDF page {rec['page']}")
    print(rec["text"][:900])