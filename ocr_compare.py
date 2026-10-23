import re
import time
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

PDF_PATH = "data/fieldbook_1.pdf"
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DPI = 300

# phrases that really are on these pages (taken from the page previews)
CHECKS = {
    30: [
        "cryptically patterned plumages",
        "to escape detection",
        "Coursers and pratincoles have arched",
        "Gulls are medium-sized to large birds",
        "stout bill, moderately long legs",
        "Sandpipers, stints, Dunlin",
    ],
    200: [
        "mauve shoulder patch",
        "Sexes are similar",
        "flanks are greyer",
    ],
}

OUT_DIR = Path("ocr_test")
OUT_DIR.mkdir(exist_ok=True)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def score(text, page_no):
    t = norm(text)
    found = [p for p in CHECKS[page_no] if norm(p) in t]
    missing = [p for p in CHECKS[page_no] if p not in found]
    return len(found), len(CHECKS[page_no]), missing


def render(doc, page_no):
    pix = doc[page_no - 1].get_pixmap(dpi=DPI, colorspace=pymupdf.csRGB, alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


rapid = RapidOCR()


def rapid_text(img, **kwargs):
    result, _ = rapid(np.array(img), **kwargs)
    if not result:
        return ""
    items = []
    for box, text, conf in result:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append(((min(ys) + max(ys)) / 2, min(xs), text))
    items.sort()
    return "\n".join(t for _, _, t in items)


variants = [
    ("RapidOCR default", lambda img: rapid_text(img)),
    ("RapidOCR low thresholds", lambda img: rapid_text(img, box_thresh=0.3, text_score=0.3)),
]

try:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
    print("Tesseract version:", pytesseract.get_tesseract_version())
    variants.append(("Tesseract psm 3", lambda img: pytesseract.image_to_string(img, lang="eng", config="--psm 3")))
    variants.append(("Tesseract psm 4", lambda img: pytesseract.image_to_string(img, lang="eng", config="--psm 4")))
except Exception as e:
    print("Tesseract not available, skipping it:", e)

doc = pymupdf.open(PDF_PATH)
saved = {}

for page_no in CHECKS:
    img = render(doc, page_no)
    print(f"\n=== PDF page {page_no} (image {img.width}x{img.height}) ===")
    for name, fn in variants:
        start = time.time()
        try:
            text = fn(img)
        except Exception as e:
            print(f"{name:26s} FAILED: {e}")
            continue
        seconds = time.time() - start
        got, total, missing = score(text, page_no)
        print(f"{name:26s} {seconds:5.1f}s  {len(text):5d} chars  found {got}/{total}")
        if missing:
            print("    missing:", missing)
        out = OUT_DIR / f"p{page_no}_{re.sub(r'\W+', '_', name)}.txt"
        out.write_text(text, encoding="utf-8")
        saved[(page_no, name)] = text

key = (200, "Tesseract psm 3")
if key in saved:
    print("\n--- Tesseract psm 3, page 200, first 25 lines ---")
    for line in [l for l in saved[key].splitlines() if l.strip()][:25]:
        print("  ", line[:120])