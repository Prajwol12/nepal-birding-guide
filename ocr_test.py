import time
from pathlib import Path

import numpy as np
import pymupdf
from rapidocr_onnxruntime import RapidOCR

PDF_PATH = "data/fieldbook_1.pdf"
TEST_PAGES = [30, 200, 201, 350]  # PDF page numbers, starting at 1
DPI = 200
OUT_DIR = Path("ocr_test")
OUT_DIR.mkdir(exist_ok=True)

engine = RapidOCR()
doc = pymupdf.open(PDF_PATH)


def ocr_page(page):
    pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csRGB, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    result, _ = engine(img)
    if not result:
        return []
    items = []
    for box, text, score in result:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append({
            "text": text,
            "score": float(score),
            "x": min(xs),
            "y": (min(ys) + max(ys)) / 2,
        })
    items.sort(key=lambda d: (d["y"], d["x"]))
    return items


for page_no in TEST_PAGES:
    start = time.time()
    items = ocr_page(doc[page_no - 1])
    seconds = time.time() - start

    text = "\n".join(d["text"] for d in items)
    (OUT_DIR / f"page_{page_no}.txt").write_text(text, encoding="utf-8")

    avg = sum(d["score"] for d in items) / len(items) if items else 0
    print("=" * 60)
    print(f"PDF page {page_no}: {seconds:.1f}s, {len(items)} lines, avg confidence {avg:.2f}")
    for d in items[:25]:
        print("  ", d["text"][:120])