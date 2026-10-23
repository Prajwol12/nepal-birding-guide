import ast
import csv
import difflib
import json
import re
from collections import Counter, defaultdict

CHUNKS_PATH = "data/fieldbook_1_chunks.jsonl"
FB2_PATH = "data/fieldbook_2_chunks.jsonl"
CHECKLIST_PATH = "data/checklist.csv"
ALIAS_SCRIPT = "apply_aliases.py"
FUZZY_CUTOFF = 0.9
# fuzzy matches I checked by hand and found to be different species
REJECT_FUZZY = {"arborophila atrogularis"}

# reuse the alias table from apply_aliases.py (the file is read, not run)
ALIASES = {}
with open(ALIAS_SCRIPT, encoding="utf-8") as f:
    tree = ast.parse(f.read())
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ALIASES" for t in node.targets):
        ALIASES = ast.literal_eval(node.value)

with open(CHECKLIST_PATH, encoding="utf-8") as f:
    checklist = list(csv.DictReader(f))
by_no = {r["no"]: r for r in checklist}


def norm(s):
    return s.lower().replace("’", "'").strip()


by_sci = {norm(r["scientific_name"]): r for r in checklist}
by_eng = {norm(r["english_name"]): r for r in checklist}
alias_by_sci = {norm(k): (by_no[no], rel) for k, (no, rel) in ALIASES.items() if no in by_no}

# names used for fuzzy matching (catches OCR typos like "platyrtynchos")
fuzzy_pool = {name: row for name, row in by_sci.items()}
fuzzy_pool.update({name: row for name, (row, rel) in alias_by_sci.items()})


def link(ch):
    sci = norm(ch["scientific_name"])
    eng = norm(ch["english_name"])
    if sci in by_sci:
        return by_sci[sci], "exact"
    if sci in alias_by_sci:
        return alias_by_sci[sci]
    if eng in by_eng:
        return by_eng[eng], "exact_name"
    close = difflib.get_close_matches(sci, list(fuzzy_pool), n=1, cutoff=FUZZY_CUTOFF)
    if close and sci not in REJECT_FUZZY:
        return fuzzy_pool[close[0]], "fuzzy"
    return None, "none"


with open(CHUNKS_PATH, encoding="utf-8") as f:
    chunks = [json.loads(line) for line in f]

FIELDS = ["checklist_no", "checklist_scientific_name", "checklist_english_name",
          "order", "family", "gts", "nts", "cites"]
fuzzy_list = []
for ch in chunks:
    if ch["type"] != "species":
        continue
    for k in FIELDS:
        ch.pop(k, None)
    row, kind = link(ch)
    ch["in_checklist"] = row is not None
    ch["match_type"] = kind
    if row:
        ch.update({"checklist_no": row["no"],
                   "checklist_scientific_name": row["scientific_name"],
                   "checklist_english_name": row["english_name"],
                   "order": row["order"], "family": row["family"],
                   "gts": row["gts"], "nts": row["nts"], "cites": row["cites"]})
    if kind == "fuzzy":
        fuzzy_list.append((ch, row))

species = [c for c in chunks if c["type"] == "species"]

print(f"Fuzzy matches (already reviewed): {len(fuzzy_list)}")


def letters(s):
    return re.sub(r"[^a-z]", "", norm(s))


groups = defaultdict(list)
for c in species:
    if c["in_checklist"]:
        groups[c["checklist_no"]].append(c)
conflicts = {no: g for no, g in groups.items() if len(g) > 1}

print(f"\nChecklist species linked to more than one fieldbook_1 account: {len(conflicts)}")
removed = []
for no, g in conflicts.items():
    row = by_no[no]
    print(f"  checklist {no}: {row['english_name']} | {row['scientific_name']}")
    for c in g:
        print(f"      {c['english_name']} | {c['scientific_name']} | {c['match_type']} | p{c['page_start']}")
    keep = [c for c in g if letters(c["english_name"]) == letters(row["english_name"])
            or c["match_type"] in ("renamed", "split")]
    if not keep:
        keep = g[:1]
    for c in g:
        if not any(c is k for k in keep):
            for k in FIELDS:
                c.pop(k, None)
            c["in_checklist"] = False
            c["match_type"] = "conflict_removed"
            removed.append(c)
print(f"Links removed because another account fits the checklist name better: {len(removed)}")

with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
    for ch in chunks:
        f.write(json.dumps(ch, ensure_ascii=False) + "\n")

print("\nMatch types after cleanup:", dict(Counter(c["match_type"] for c in species)))

unmatched = [c for c in species if not c["in_checklist"]]
print(f"\nUnmatched fieldbook_1 species (mostly birds outside Nepal): {len(unmatched)}")
for c in unmatched[:10]:
    print(f"  {c['english_name']} | {c['scientific_name']} | p{c['page_start']}")

have = {c["checklist_no"] for c in species if c["in_checklist"]}
try:
    with open(FB2_PATH, encoding="utf-8") as f:
        have |= {c["checklist_no"] for c in map(json.loads, f) if c.get("type") == "species" and c.get("in_checklist")}
except FileNotFoundError:
    print("\n(fieldbook_2_chunks.jsonl not found)")
none = [r for r in checklist if r["no"] not in have]
print(f"\nChecklist species with no account in either book: {len(none)}")
for r in none[:60]:
    print(f"  {r['no']} {r['english_name']} | {r['scientific_name']}")