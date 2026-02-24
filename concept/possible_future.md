# Possible Future Features

Interesting Python libraries that could make bibtui even more magical.
Grouped by effort and impact.

---

## Low Effort, High Impact

### `rapidfuzz` — Duplicate Detection

Scan the `.bib` file for near-identical titles and flag them. Huge for large collections.

```
uv add rapidfuzz
```

**How it fits:** A "Find duplicates" command in the command palette scans all entries
pairwise. Pairs where `token_set_ratio(a.title, b.title) > 85` and author surnames
overlap get presented in a modal for the user to merge or dismiss. Also useful as a
real-time warning in the DOI import flow.

```python
from rapidfuzz import fuzz

def find_duplicates(entries: list[BibEntry], threshold: int = 85):
    dupes = []
    for i, a in enumerate(entries):
        for b in entries[i+1:]:
            if fuzz.token_set_ratio(a.title, b.title) >= threshold:
                dupes.append((a, b))
    return dupes
```

---

### `pymupdf` + `pymupdf4llm` — PDF Full-Text Search

The fastest Python PDF library (wins every benchmark). `pymupdf4llm` extracts PDF
content as clean Markdown, ideal for feeding to LLMs.

```
uv add pymupdf pymupdf4llm
```

**How it fits:**
- Press a keybinding on a selected entry to **search inside the linked PDF** — uses
  `BibEntry.file` which already exists.
- **Auto-populate missing abstracts** by parsing the first two pages.
- Render a **cover page thumbnail** in the `AddPDFModal` (already has preview logic).
- Extract text to feed to an LLM for summarization.

```python
import fitz  # pymupdf

def search_pdf(pdf_path: str, query: str) -> list[tuple[int, str]]:
    doc = fitz.open(pdf_path)
    hits = []
    for page_num, page in enumerate(doc, start=1):
        rects = page.search_for(query)
        if rects:
            hits.append((page_num, page.get_text("text", clip=rects[0])[:200]))
    return hits
```

---

### `semanticscholar` — Citation Counts and Recommendations

Free Semantic Scholar API (225M+ papers). No auth required for basic use.

```
uv add semanticscholar
```

**How it fits:**
- Show **citation count** in `EntryDetail` — something Crossref/habanero doesn't
  reliably provide.
- New action "Recommended papers": fetches 5 related papers and presents them with
  a DOI-import button, reusing the existing `DOIModal` architecture.
- Fallback in `fetch_by_doi` for missing abstracts.

```python
from semanticscholar import SemanticScholar

sch = SemanticScholar()

def get_citation_count(doi: str) -> int | None:
    try:
        paper = sch.get_paper(f"DOI:{doi}", fields=["citationCount"])
        return paper.citationCount
    except Exception:
        return None
```

---

### `arxiv` — arXiv Search Modal

Official arXiv Python client. Search by title, author, or category.

```
uv add arxiv
```

**How it fits:** A new "Search arXiv" modal that mirrors `DOIModal` exactly — user
types a title fragment or author name, sees a scrollable list of matching papers with
abstracts, and imports selected ones directly.

```python
import arxiv

def search_arxiv(query: str, max_results: int = 10) -> list[dict]:
    client = arxiv.Client()
    search = arxiv.Search(query=query, max_results=max_results,
                          sort_by=arxiv.SortCriterion.Relevance)
    return [
        {
            "title": p.title,
            "authors": [str(a) for a in p.authors],
            "year": str(p.published.year),
            "abstract": p.summary,
            "doi": p.doi or "",
            "pdf_url": p.pdf_url,
        }
        for p in client.results(search)
    ]
```

---

### `textual-plotext` — Terminal Charts

Official Textualize widget wrapping `plotext`. Uses Braille Unicode for sub-character
resolution — looks completely native in the terminal.

```
uv add textual-plotext
```

**How it fits:** A statistics panel (new keybinding or tab) showing:
- Papers per year (bar chart)
- Read-state and ratings breakdown
- Citation growth sparkline per entry (data from Semantic Scholar or OpenAlex)
- "Collection health" dashboard: % with abstracts, % with PDFs, % read

```python
from textual_plotext import PlotextPlot

class YearHistogram(PlotextPlot):
    def on_mount(self) -> None:
        years = [e.year for e in self.app.entries if e.year]
        self.plt.bar(sorted(set(years)),
                     [years.count(y) for y in sorted(set(years))])
        self.plt.title("Papers per year")
        self.plt.theme("dark")
        self.refresh()
```

---

### `pypandoc` — Export to Other Formats

Wraps Pandoc. Reads BibTeX and outputs RIS, CSL-JSON, APA HTML, and more.

```
uv add pypandoc  # also requires pandoc binary on PATH
```

**How it fits:** A command palette action "Export bibliography" — export the whole
file or only filtered/selected entries to RIS (Mendeley/Zotero/EndNote),
CSL-JSON (Quarto, Obsidian), or a formatted HTML reference list.

---

## Medium Effort, Genuinely Magical

### `fastembed` + `numpy` — "Find Similar Papers"

FastEmbed uses ONNX Runtime instead of PyTorch — fast on CPU, no GPU needed,
no multi-GB torch dependency. Model download ~130MB on first use.

```
uv add fastembed numpy
```

**How it fits:** Embed all `title + abstract` fields once, store vectors in a
`.npy` file next to the `.bib` file. New action "Find similar papers" returns the
top-5 most semantically similar entries to the currently selected one. No external
server needed.

```python
from fastembed import TextEmbedding
import numpy as np

def build_index(entries):
    model = TextEmbedding("BAAI/bge-small-en-v1.5")
    texts = [f"{e.title} {e.abstract}" for e in entries]
    return np.array(list(model.embed(texts)), dtype="float32")

def find_similar(query_idx: int, matrix: np.ndarray, top_k: int = 5):
    q = matrix[query_idx]
    scores = matrix @ q / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(q) + 1e-9)
    scores[query_idx] = -1
    return np.argsort(scores)[::-1][:top_k].tolist()
```

---

### `ollama` — Local LLM Integration

Official Ollama Python client. Talks to a locally running Ollama daemon. Gracefully
degrades with a clear message when Ollama is not installed.

```
uv add ollama
```

**How it fits:**
- New keybinding: **"Summarize this paper"** — sends abstract (+ PDF text via pymupdf
  if available) to a local model (`gemma3:4b`, `llama3.2:3b`) and shows a plain-
  English summary in a modal.
- **Auto-suggest keywords** — prompt the LLM with title + abstract, propose 5 new
  keywords not already in `BibEntry.keywords`. User accepts/rejects before writing.
- **Natural language search mode** — type "papers about glacier melt and ML" instead
  of `k:glacier j:nature`.

```python
import ollama

def summarize(title: str, abstract: str, model: str = "gemma3:4b") -> str:
    prompt = (
        f"Summarize this academic paper in 2-3 sentences.\n"
        f"Title: {title}\nAbstract: {abstract}"
    )
    try:
        resp = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return resp.message.content
    except Exception as exc:
        return f"Ollama unavailable: {exc}"
```

---

## The Full Magic Stack

### `txtai` — Natural Language Querying (Local RAG)

Combines embeddings, a vector index, and an optional LLM into one object that
persists to a single SQLite file. No separate server required.

```
uv add txtai
```

**How it fits:** Index all abstracts, titles, keywords, and (optionally) full PDF
text. Let the user type natural language queries like:

> *"deep learning applied to glacier melt before 2020"*

and get semantically ranked results — not keyword matches. The index lives at
`~/.local/share/bibtui/index/` and rebuilds automatically when the `.bib` mtime
changes.

```python
from txtai.embeddings import Embeddings

class BibIndex:
    def __init__(self, index_path: str):
        self.emb = Embeddings({"path": "sentence-transformers/all-MiniLM-L6-v2",
                                "content": True})
        self.index_path = index_path

    def build(self, entries: list[BibEntry]) -> None:
        docs = [(i, f"{e.title}. {e.abstract}. Keywords: {e.keywords}", None)
                for i, e in enumerate(entries)]
        self.emb.index(docs)
        self.emb.save(self.index_path)

    def search(self, query: str, limit: int = 5) -> list[int]:
        return [r["id"] for r in self.emb.search(query, limit=limit)]
```

---

## Other Honorable Mentions

| Library | Use |
|---|---|
| `pyalex` | OpenAlex open citation graph, co-citation analysis, citation timeline per year |
| `nameparser` | Smarter cite-key generation in JabRef style (`smith2023title`) |
| `textual-image` | Render PDF cover page thumbnail in terminal (best in Kitty/WezTerm) |

---

## Suggested Implementation Order

1. **`rapidfuzz`** — 30 lines, immediate value for large `.bib` files
2. **`pymupdf`** — PDF text search + cover preview, builds on existing `BibEntry.file` logic
3. **`semanticscholar`** — citation counts + recommendations, extends existing `fetch_by_doi`
4. **`arxiv`** — search modal, mirrors existing `DOIModal` architecture
5. **`textual-plotext`** — stats panel, pure UI addition
6. **`fastembed`** — semantic similarity, no server needed
7. **`ollama`** — local LLM, optional and gracefully degraded
8. **`txtai`** — full NL querying, the end goal
