import json
import time
import unicodedata
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

PDF_PATH = "data/fieldbook_1.pdf"
OUT_PATH = Path("data/fieldbook_1_ocr.jsonl")
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DPI = 300
LOW_TEXT = 300  # pages with fewer characters are probably illustration plates

pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE

doc = pymupdf.open(PDF_PATH)
total = len(doc)

# make sure the file ends with a newline (in case a previous run was interrupted mid-write)
if OUT_PATH.exists() and OUT_PATH.stat().st_size > 0:
    with open(OUT_PATH, "rb") as f:
        f.seek(-1, 2)
        last_byte = f.read(1)
    if last_byte != b"\n":
        with open(OUT_PATH, "a", encoding="utf-8") as g:
            g.write("\n")

# pages already finished in an earlier run
done = set()
if OUT_PATH.exists():
    with open(OUT_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                done.add(json.loads(line)["page"])
            except Exception:
                pass  # skip a half-written line

todo = [p for p in range(1, total + 1) if p not in done]
print(f"{total} pages in total, {len(done)} already done, {len(todo)} to go")

start = time.time()
with open(OUT_PATH, "a", encoding="utf-8") as out:
    for n, page_no in enumerate(todo, start=1):
        try:
            pix = doc[page_no - 1].get_pixmap(dpi=DPI, colorspace=pymupdf.csRGB, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 3")
        except Exception as e:
            print(f"page {page_no} FAILED: {e}")
            continue

        text = unicodedata.normalize("NFKC", text)
        out.write(json.dumps({"page": page_no, "text": text}, ensure_ascii=False) + "\n")
        out.flush()

        if n % 10 == 0 or n == len(todo):
            elapsed = time.time() - start
            left = elapsed / n * (len(todo) - n)
            print(f"page {page_no} done ({n}/{len(todo)}), {elapsed / 60:.1f} min elapsed, about {left / 60:.1f} min left")

# ---- summary ----
pages = []
with open(OUT_PATH, encoding="utf-8") as f:
    for line in f:
        try:
            pages.append(json.loads(line))
        except Exception:
            pass

low = [p["page"] for p in pages if len(p["text"].strip()) < LOW_TEXT]
print("\n=== SUMMARY ===")
print(f"Pages OCR'd: {len(pages)} of {total}")
print(f"Total characters: {sum(len(p['text']) for p in pages)}")
print(f"Pages with little text (likely plates): {len(low)}")
print("First 30 of those:", low[:30])
missing = sorted(set(range(1, total + 1)) - {p["page"] for p in pages})
print("Pages that failed or are missing:", missing)