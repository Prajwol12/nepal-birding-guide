import csv
import difflib
import json
import re
import statistics
import time
from collections import Counter
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

CHECKLIST_PATH = "data/checklist.csv"
FB1_PATH = "data/fieldbook_1_chunks.jsonl"
FB2_PATH = "data/fieldbook_2_chunks.jsonl"
OUT_DIR = Path("index")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
MAX_CHARS = 1500  # longer texts are split into pieces

# Replace these with the real book titles; they appear in citations later.
SOURCE_LABELS = {
    "fieldbook_1": "Fieldbook 1",
    "fieldbook_2": "Fieldbook 2",
    "checklist": "Official checklist",
}

THREAT = {"CR": "Critically Endangered (CR)", "EN": "Endangered (EN)", "VU": "Vulnerable (VU)"}
NONE_LISTED = "no threat category (CR, EN or VU) listed"
SIZE_RE = re.compile(r"\d+\s?(?:[–-]\s?\d+)?\s?cm")


def norm(s):
    return s.lower().replace("’", "'").strip()


def split_text(text, limit=MAX_CHARS):
    """Split long text at sentence ends, repeating one sentence between pieces."""
    if len(text) <= limit:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    parts, cur, last = [], "", ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > limit:
            parts.append(cur)
            cur = (last + " " + s).strip() if 0 < len(last) < 300 else s
        else:
            cur = (cur + " " + s).strip()
        last = s
    if cur:
        parts.append(cur)
    return parts


chunks = []


def add(source, ctype, title, body, note=None, **meta):
    for i, piece in enumerate(split_text(body.strip())):
        lines = [title if i == 0 else f"{title} (continued)"]
        if note and i == 0:
            lines.append(note)
        lines.append(piece)
        chunks.append({"id": len(chunks), "source": source, "type": ctype,
                       "title": title, "text": "\n".join(lines), **meta})


# ---- 1. one chunk per checklist entry ----
with open(CHECKLIST_PATH, encoding="utf-8") as f:
    checklist = list(csv.DictReader(f))
by_no = {r["no"]: r for r in checklist}

for r in checklist:
    shown_no = re.sub(r"b+$", "", r["no"])
    body = (f"Official Nepal checklist entry no. {shown_no}. Order {r['order']}, family {r['family']}. "
            f"Global threat status (GTS): {THREAT.get(r['gts'], NONE_LISTED)}. "
            f"National threat status in Nepal (NTS): {THREAT.get(r['nts'], NONE_LISTED)}. "
            f"CITES: {'Appendix ' + r['cites'] if r['cites'] else 'not listed'}.")
    add("checklist", "checklist", f"{r['english_name']} ({r['scientific_name']})", body,
        english_name=r["english_name"], scientific_name=r["scientific_name"],
        checklist_no=r["no"], family=r["family"], order=r["order"],
        gts=r["gts"], nts=r["nts"], cites=r["cites"])

# ---- 2. the two fieldbooks ----
for source, path in (("fieldbook_2", FB2_PATH), ("fieldbook_1", FB1_PATH)):
    with open(path, encoding="utf-8") as f:
        items = [json.loads(line) for line in f]
    label = SOURCE_LABELS[source]
    for c in items:
        t = c["type"]
        if t == "species":
            if not c.get("in_checklist"):
                continue  # birds outside Nepal
            row = by_no[c["checklist_no"]]
            ck_eng, ck_sci = row["english_name"], row["scientific_name"]
            first, _, body = c["text"].partition("\n")
            size = SIZE_RE.search(first)
            if size and source == "fieldbook_1":
                body = f"Size: {size.group(0)}. {body}"
            kind = c.get("match_type", "exact")
            ratio = difflib.SequenceMatcher(None, norm(c["scientific_name"]), norm(ck_sci)).ratio()
            note = None
            if kind in ("renamed", "split") or (kind == "exact_name" and ratio < 0.85):
                note = (f"Taxonomy note: {label} calls this bird {c['english_name']} "
                        f"({c['scientific_name']}); the official Nepal checklist lists it as "
                        f"{ck_eng} ({ck_sci}).")
                if kind == "split":
                    note += " The two sources treat the species differently (split or lumped)."
            add(source, "species", f"{ck_eng} ({ck_sci})", body, note=note,
                english_name=ck_eng, scientific_name=ck_sci, checklist_no=c["checklist_no"],
                family=row["family"], order=row["order"], gts=row["gts"], nts=row["nts"],
                cites=row["cites"], pdf_page=c["page_start"], match_type=kind)
        elif t == "family":
            first, _, body = c["text"].partition("\n")
            add(source, "family", f"Family summary: {first}", body, pdf_page=c["page_start"])
        elif t in ("general", "appendix"):
            if source == "fieldbook_1" and c["page_start"] <= 9:
                continue  # title page, contents, copyright
            if len(c["text"]) < 150:
                continue
            add(source, t, f"{label}, general text (PDF page {c['page_start']})", c["text"],
                pdf_page=c["page_start"])

OUT_DIR.mkdir(exist_ok=True)
with open(OUT_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
    for c in chunks:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")

print(f"Total chunks: {len(chunks)}")
for key, n in sorted(Counter((c["source"], c["type"]) for c in chunks).items()):
    print(f"  {key[0]:12s} {key[1]:10s} {n}")
lens = sorted(len(c["text"]) for c in chunks)
print(f"Text length: min {lens[0]}, median {statistics.median(lens):.0f}, max {lens[-1]}")
species_with_text = {c["checklist_no"] for c in chunks if c["type"] == "species"}
print(f"Checklist species that have at least one field-guide account: {len(species_with_text)} of {len(checklist)}")

# ---- 3. embeddings ----
print(f"\nEmbedding {len(chunks)} chunks with {MODEL_NAME} (first run downloads the model)...")
start = time.time()
model = TextEmbedding(model_name=MODEL_NAME)
vecs = np.array(list(model.embed([c["text"] for c in chunks], batch_size=32)), dtype="float32")
vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
np.save(OUT_DIR / "embeddings.npy", vecs)
print(f"Done in {time.time() - start:.0f}s, matrix shape {vecs.shape}")

# ---- 4. test searches ----
QUERIES = [
    "What is the conservation status of the Pin-tailed Green Pigeon?",
    "How do I tell a Verditer Flycatcher apart from other flycatchers?",
    "What does the Collared Owlet sound like?",
    "Which birds are critically endangered in Nepal?",
    "Where are good places to go birdwatching in Nepal?",
    "Was the Spotted Dove split into separate species?",
]
for q in QUERIES:
    qv = np.array(list(model.embed([q]))[0], dtype="float32")
    qv /= np.linalg.norm(qv)
    top = np.argsort(-(vecs @ qv))[:3]
    print("\nQ:", q)
    for i in top:
        c = chunks[i]
        print(f"   {float(vecs[i] @ qv):.2f} [{c['source']}/{c['type']}] {c['title'][:70]}")