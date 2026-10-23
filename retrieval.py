import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

INDEX_DIR = Path(__file__).parent / "index"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

# Replace with the real book titles; used in the source lines the chatbot cites.
SOURCE_LABELS = {
    "fieldbook_1": "Birds of the Indian Subcontinent",
    "fieldbook_2": "Birds of Nepal",
    "checklist": "Official checklist",
}

CODES = {"CR": "Critically Endangered (CR)", "EN": "Endangered (EN)", "VU": "Vulnerable (VU)"}
ALIAS_RE = re.compile(r"calls this bird (.+?) \((.+?)\); the official")
MAX_CONTEXT_CHARS = 12000
MAX_LIST = 150


def words(s):
    """'Pin-tailed Green-pigeon' -> 'pin tailed green pigeon' (apostrophes dropped, punctuation to spaces)."""
    s = s.lower().replace("’", "").replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


class Retriever:
    def __init__(self):
        with open(INDEX_DIR / "chunks.jsonl", encoding="utf-8") as f:
            self.chunks = [json.loads(line) for line in f]
        self.vecs = np.load(INDEX_DIR / "embeddings.npy")
        self.model = TextEmbedding(model_name=MODEL_NAME)

        self.species = {}         # checklist_no -> checklist chunk
        self.by_species = {}      # checklist_no -> chunk indices, checklist entry first
        self.names = defaultdict(set)  # normalised name -> {checklist_no}
        extra = defaultdict(list)
        for i, c in enumerate(self.chunks):
            if c["type"] == "checklist":
                no = c["checklist_no"]
                self.species[no] = c
                self.by_species[no] = [i]
                for n in (c["english_name"], c["scientific_name"]):
                    self.names[words(n)].add(no)
            elif c["type"] == "species":
                extra[c["checklist_no"]].append(i)
                m = ALIAS_RE.search(c["text"])
                if m:  # names the field guides use for this bird
                    for n in (m.group(1), m.group(2)):
                        self.names[words(n)].add(c["checklist_no"])
        for no, idx in extra.items():
            self.by_species[no].extend(idx)
        self.names = {n: nos for n, nos in self.names.items() if len(n) >= 4}

    # ---- finding bird names in the question ----
    def find_species(self, query):
        q = " " + words(query) + " "
        found = [n for n in self.names if f" {n} " in q]
        if not found:  # tolerate "wood pigeon" vs "woodpigeon"
            qn = q.replace(" ", "")
            found = [n for n in self.names if len(n) >= 8 and n.replace(" ", "") in qn]
        found.sort(key=len, reverse=True)
        kept = []
        for n in found:  # drop names that sit inside a longer matched name
            if not any(f" {n} " in f" {k} " for k in kept):
                kept.append(n)
        numbers = []
        for n in kept:
            for no in sorted(self.names[n]):
                if no not in numbers:
                    numbers.append(no)
        return numbers[:4]

    # ---- list questions answered from the checklist table ----
    def status_block(self, query, has_species):
        ql = query.lower()
        listy = re.search(r"\b(which|list|what birds|what species|how many|name the|all the|all)\b", ql)
        if has_species and not listy:
            return None

        levels = []
        if "critically endangered" in ql:
            levels.append("CR")
        if "endangered" in ql.replace("critically endangered", ""):
            levels.append("EN")
        if "vulnerable" in ql:
            levels.append("VU")
        if not levels and re.search(r"threatened|threat status|red list|conservation concern|at risk", ql):
            levels = ["CR", "EN", "VU"]

        cites = re.findall(r"appendix\s+(iii|ii|i|1|2|3)\b", ql)
        cites = [{"1": "I", "2": "II", "3": "III"}.get(c, c.upper()) for c in cites]
        if not levels and not cites:
            return None

        if re.search(r"global|worldwide|iucn|world", ql):
            fields = [("gts", "Global threat status (GTS)")]
        elif re.search(r"nepal|national|country", ql):
            fields = [("nts", "National threat status in Nepal (NTS)")]
        else:
            fields = [("nts", "National threat status in Nepal (NTS)"), ("gts", "Global threat status (GTS)")]

        out = ["Complete lists from the official Nepal checklist table. Only the categories CR, EN and VU are "
               "recorded there, so a bird missing from a list has no such category in the checklist."]
        if levels:
            for field, label in fields:
                for lv in levels:
                    names = [f"{c['english_name']} ({c['scientific_name']})"
                             for c in self.species.values() if c[field] == lv]
                    shown = "; ".join(names[:MAX_LIST])
                    more = f" ... and {len(names) - MAX_LIST} more" if len(names) > MAX_LIST else ""
                    out.append(f"{label}, {CODES[lv]}: {len(names)} species. {shown}{more}")
        for ap in cites:
            names = [f"{c['english_name']} ({c['scientific_name']})"
                     for c in self.species.values() if c["cites"] == ap]
            shown = "; ".join(names[:MAX_LIST])
            more = f" ... and {len(names) - MAX_LIST} more" if len(names) > MAX_LIST else ""
            out.append(f"CITES Appendix {ap}: {len(names)} species. {shown}{more}")
        return {"source": "checklist", "type": "table", "title": "Checklist lists by status",
                "text": "\n".join(out)}

    # ---- main entry point ----
    def retrieve(self, query, k=6):
        numbers = self.find_species(query)
        included = []
        for no in numbers:
            included.extend(self.by_species[no])
        included = included[:10]

        block = self.status_block(query, bool(numbers))

        qv = np.array(list(self.model.embed([query]))[0], dtype="float32")
        qv /= np.linalg.norm(qv)
        scores = self.vecs @ qv
        order = np.argsort(-scores)
        want = max(2, k - 2) if numbers else k
        hits = [int(i) for i in order if int(i) not in included][:want]

        chosen = [self.chunks[i] for i in included]
        if block:
            chosen.append(block)
        chosen.extend(self.chunks[i] for i in hits)

        total, kept = 0, []
        for c in chosen:
            if total + len(c["text"]) > MAX_CONTEXT_CHARS and kept:
                break
            kept.append(c)
            total += len(c["text"])
        matched = [f"{self.species[no]['english_name']} ({self.species[no]['scientific_name']})" for no in numbers]
        return {"chunks": kept, "matched": matched, "top_score": float(scores[order[0]])}


def format_context(chunks):
    parts = []
    for n, c in enumerate(chunks, start=1):
        label = SOURCE_LABELS.get(c["source"], c["source"])
        page = f" (PDF page {c['pdf_page']})" if c.get("pdf_page") else ""
        title = "general text" if c["type"] in ("general", "appendix") else c["title"]
        text = c["text"]
        if c["type"] in ("general", "appendix"):
            text = text.split("\n", 1)[-1]  # the title line adds nothing here
        text = text.replace("Fieldbook 1", SOURCE_LABELS["fieldbook_1"])
        text = text.replace("Fieldbook 2", SOURCE_LABELS["fieldbook_2"])
        parts.append(f"[{n}] {label}{page} - {title}\n{text}")
    return "\n\n".join(parts)
if __name__ == "__main__":
    retriever = Retriever()
    tests = [
        "What is the conservation status of the Pin-tailed Green Pigeon?",
        "Was the Spotted Dove split into separate species?",
        "What is the difference between a Verditer Flycatcher and a Pale Blue Flycatcher?",
        "Which birds are critically endangered in Nepal?",
        "Which birds are listed in CITES Appendix I?",
        "Is the Great Hornbill threatened?",
        "Where are good places to go birdwatching in Nepal?",
        "What is the capital of France?",
    ]
    for q in tests:
        r = retriever.retrieve(q)
        print("\nQ:", q)
        print(f"   matched birds: {r['matched']}   best similarity: {r['top_score']:.2f}")
        for c in r["chunks"]:
            page = f" p{c['pdf_page']}" if c.get("pdf_page") else ""
            print(f"   - [{c['source']}/{c['type']}{page}] {c['title'][:70]}")
        for c in r["chunks"]:
            if c["type"] == "table":
                print("   table preview:", c["text"][:300].replace("\n", " | "))