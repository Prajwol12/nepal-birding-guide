import json

TARGETS = ["Satyr Tragopan", "Indian Peafowl", "Himalayan Monal", "Red Junglefowl", "Kalij Pheasant"]

with open("data/fieldbook_2_pages.jsonl", encoding="utf-8") as f:
    pages = [json.loads(line) for line in f]

print("PART 1: header and next 3 lines for species the chunker missed")
for target in TARGETS:
    shown = 0
    for rec in pages:
        lines = rec["text"].splitlines()
        for i, line in enumerate(lines):
            if target in line and shown < 2:
                shown += 1
                print(f"\n--- {target} (pdf page {rec['page']}) ---")
                for l in lines[i:i + 4]:
                    print("   ", l[:110])

print("\n\nPART 2: pages near the end of the book")
for rec in pages:
    if rec["page"] >= 350:
        first_lines = rec["text"].splitlines()[:3]
        print(f"page {rec['page']} ({len(rec['text'])} chars):", " / ".join(l[:60] for l in first_lines))