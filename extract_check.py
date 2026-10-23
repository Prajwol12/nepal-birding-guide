import pdfplumber
from pathlib import Path

DATA_DIR = Path("data")
SAMPLE_PAGE = 10  # page index to preview (0 = first page)

for pdf_path in sorted(DATA_DIR.glob("*.pdf")):
    print("=" * 60)
    print(pdf_path.name)
    with pdfplumber.open(pdf_path) as pdf:
        total_chars = 0
        pages_with_tables = 0
        for page in pdf.pages:
            total_chars += len(page.extract_text() or "")
            if page.extract_tables():
                pages_with_tables += 1

        print(f"Pages: {len(pdf.pages)}")
        print(f"Total characters extracted: {total_chars}")
        print(f"Pages with tables: {pages_with_tables}")

        if SAMPLE_PAGE < len(pdf.pages):
            page = pdf.pages[SAMPLE_PAGE]
            print(f"\n--- Text preview (page {SAMPLE_PAGE + 1}) ---")
            print((page.extract_text() or "")[:500])
            tables = page.extract_tables()
            if tables:
                print(f"\n--- First 3 rows of first table ---")
                for row in tables[0][:3]:
                    print(row)