import csv
import json
from collections import Counter

CHUNKS_PATH = "data/fieldbook_2_chunks.jsonl"
CHECKLIST_PATH = "data/checklist.csv"

# fieldbook scientific name -> (checklist number, relation)
#   renamed = same species, now under a new name in the official checklist
#   split   = taxonomy differs (species split or lumped); closest checklist species
ALIASES = {
    "Coturnix chinensis": ("6", "renamed"),
    "Casmerodius albus": ("167", "renamed"),
    "Nisaetus limnaeetus": ("288", "split"),
    "Porzana pusilla": ("128", "renamed"),
    "Charadrius mongolus": ("187", "split"),
    "Ichthyaetus ichthyaetus": ("235", "renamed"),
    "Stigmatopelia chinensis": ("73", "split"),
    "Hierococcyx fugax": ("115", "split"),
    "Surniculus lugubris": ("112", "split"),
    "Dendrocopos nanus": ("368", "renamed"),
    "Dendrocopos canicapillus": ("367", "renamed"),
    "Dendrocopos cathpharius": ("371", "renamed"),
    "Chrysocolaptes lucidus": ("355", "split"),
    "Chelidorhynx hypoxantha": ("457", "renamed"),
    "Nucifraga caryocatactes": ("453", "split"),
    "Garrulus glandarius": ("451", "split"),
    "Aegithalos concinnus": ("577", "split"),
    "Riparia paludicola": ("525", "split"),
    "Prinia burnesii": ("614", "renamed"),
    "Cettia pallidipes": ("566", "renamed"),
    "Cettia fortipes": ("573", "renamed"),
    "Cettia flavolivacea": ("575", "renamed"),
    "Cettia brunnescens": ("574", "renamed"),
    "Bradypterus thoracicus": ("514", "renamed"),
    "Bradypterus tacsanowskius": ("510", "renamed"),
    "Seicercus whistleri": ("552", "renamed"),
    "Pomatorhinus erythrogenys": ("603", "renamed"),
    "Xiphirhynchus superciliaris": ("600", "renamed"),
    "Rimator malacoptilus": ("617", "renamed"),
    "Sphenocichla humei": ("605", "renamed"),
    "Macronus gularis": ("608", "renamed"),
    "Pteruthius flaviscapis": ("405", "split"),
    "Siva strigula": ("651", "renamed"),
    "Luscinia pectoralis": ("732", "renamed"),
    "Brachypteryx montana": ("725", "split"),
    "Rhyacornis fuliginosa": ("762", "renamed"),
    "Chaimarrornis leucocephalus": ("761", "renamed"),
    "Monticola cinclorhynchus": ("767", "renamed"),
    "Cercomela fusca": ("781", "renamed"),
    "Serinus thibetanus": ("885", "renamed"),
    "Carduelis carduelis": ("883", "split"),
    "Carpodacus rubescens": ("873", "renamed"),
    "Serilophus lunatus": ("398", "split"),
    "Bradypterus davidi": ("512", "renamed"),
    "Bradypterus luteoventris": ("509", "renamed"),
    "Locustella certhiola": ("507", "renamed"),
    "Carduelis cannabina": ("881", "renamed"),
}

with open(CHECKLIST_PATH, encoding="utf-8") as f:
    checklist = list(csv.DictReader(f))
by_no = {r["no"]: r for r in checklist}

with open(CHUNKS_PATH, encoding="utf-8") as f:
    chunks = [json.loads(line) for line in f]

for ch in chunks:
    if ch["type"] != "species":
        continue
    if ch["in_checklist"]:
        ch.setdefault("match_type", "exact")
        continue
    alias = ALIASES.get(ch["scientific_name"])
    if not alias:
        continue
    no, relation = alias
    row = by_no[no]
    ch.update({
        "in_checklist": True,
        "match_type": relation,
        "checklist_no": row["no"],
        "checklist_scientific_name": row["scientific_name"],
        "checklist_english_name": row["english_name"],
        "order": row["order"],
        "family": row["family"],
        "gts": row["gts"],
        "nts": row["nts"],
        "cites": row["cites"],
    })

with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
    for ch in chunks:
        f.write(json.dumps(ch, ensure_ascii=False) + "\n")

species = [c for c in chunks if c["type"] == "species"]
print("Match types:", dict(Counter(c.get("match_type", "none") for c in species)))
print("Alias names not found in any fieldbook account (typos?):", sorted(set(ALIASES) - {c["scientific_name"] for c in species}))

print("\nStill unmatched fieldbook accounts:")
for c in species:
    if not c["in_checklist"]:
        print("  ", c["english_name"], "|", c["scientific_name"], "| p", c["page_start"])

found = {c["checklist_no"] for c in species if c["in_checklist"]}
missing = [r for r in checklist if r["no"] not in found]
print(f"\nChecklist species with no fieldbook_2 account: {len(missing)} (to be covered by fieldbook_1 or the checklist alone)")