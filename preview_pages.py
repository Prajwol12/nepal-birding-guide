import fitz  # PyMuPDF
from pathlib import Path

OUT = Path("preview")
OUT.mkdir(exist_ok=True)

# (file, list of page numbers as you'd see them in a PDF viewer, starting at 1)
SAMPLES = {
    "checklist.pdf": [11],
    "fieldbook_1.pdf": [30, 200],
    "fieldbook_2.pdf": [11, 100, 250],
}

for name, pages in SAMPLES.items():
    doc = fitz.open(Path("data") / name)
    for p in pages:
        if p <= len(doc):
            pix = doc[p - 1].get_pixmap(dpi=100)
            out_file = OUT / f"{Path(name).stem}_p{p}.png"
            pix.save(out_file)
            print("saved", out_file)