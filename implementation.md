# Implementation guide (phased)

Use this file to drive Cursor **one phase at a time**. Do not ask it to “build the whole RAG app” in a single prompt.

**Read first:** [PRD.md](./PRD.md) · [architecture.md](./architecture.md)

**How to use with Cursor**

1. Complete a phase, then check its **Done when** list yourself (or ask Cursor to verify).
2. Paste only the **Cursor prompt** for the next phase. Attach `@Milestone-4/architecture.md` (and this file if useful).
3. Do not skip phases. Later phases assume artifacts from earlier ones (`data/raw/`, `chunks.txt`, Chroma persist).
4. If a phase changes chunking or metadata, update `architecture.md` in the same change.

**Global rules for every prompt**

- Follow `architecture.md` over improvisation.
- Full RAG only: Load → Chunk → Embed → Store, then Question → Embed → Retrieve → LLM → Answer.
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (384-d), same model for chunks and queries. No embedding API.
- Vector DB: ChromaDB on disk (`data/chroma`). Collection `mf_faq`.
- LLM: Groq only; key in `.env`, never commit.
- Public AMC/AMFI sources only. Facts-only. One citation URL per answer. No PII storage.

---

## Phase 0 — Repo skeleton and secrets

**Goal:** Empty but correct project layout so later phases have a place to land.

**Create**

- `requirements.txt` (placeholders OK; versions filled as you add libs)
- `.gitignore` including `.env`, `data/raw/`, `data/chroma/`, `__pycache__/`, `.venv/`
- `.env.example` with `GROQ_API_KEY=` and optional `GROQ_MODEL=llama-3.1-8b-instant`
- `.env` locally (user fills the key; never commit)
- Directories: `src/`, `data/raw/`, `data/processed/`
- `src/__init__.py`

**Do not:** download sources, call Groq, or write ingest/app logic.

**Done when**

- Layout matches architecture §7.
- `.gitignore` would block `.env` and Chroma data.
- `python -c "import src"` works from `Milestone-4/` (or package path is documented).

**Cursor prompt (copy)**

```
Implement Phase 0 only from Milestone-4/implementation.md.

Read Milestone-4/architecture.md §7 and §8.

Create the repo skeleton: requirements.txt, .gitignore, .env.example, src/__init__.py, and empty data/raw and data/processed dirs. Add .env to gitignore. Do not download documents, do not add RAG code, do not create .env with a real key.

Stop when Phase 0 "Done when" is satisfied. Summarize files created.
```

---

## Phase 1 — Source catalog

**Goal:** The six official URLs and default metadata in one module. No fetching yet.

**Create:** `src/catalog.py`

Each entry must include:

| Field | Values |
| --- | --- |
| `source_id` | Stable slug (`flexicap-html`, `flexicap-factsheet`, `elss-factsheet`, `elss-sid`, `amc-factsheet-2025-04`, `investor-services`) |
| `url` | Exact PRD URL |
| `title` | Human label |
| `doc_type` | `scheme_page` \| `factsheet` \| `sid` \| `investor_services` |
| `scheme` | `flexicap` \| `elss` \| `largecap` \| `general` |
| `format` | `html` \| `pdf` |

Defaults: Investor Services and the complete AMC factsheet use `scheme=general` (AMC factsheet pages get retagged in Phase 3). Flexi Cap docs → `flexicap`. ELSS factsheet + SID → `elss`.

**Done when**

- Exactly six catalog entries; URLs match PRD §5.2 character-for-character.
- A one-liner or `if __name__` print lists `source_id` + url.

**Cursor prompt (copy)**

```
Implement Phase 1 only from Milestone-4/implementation.md.

Read Milestone-4/PRD.md §5.2 and Milestone-4/architecture.md §3 and §4.1.

Create src/catalog.py with exactly the six official sources and required metadata fields. Do not fetch URLs. Do not add loaders.

Stop when Phase 1 "Done when" is satisfied. Print the catalog summary.
```

---

## Phase 2 — Load (HTML + PDF → text)

**Goal:** Download or cache each source and extract inspectable text. **Inspect before chunking.**

**Create:** `src/load.py` (and a small CLI entry, e.g. `python -m src.load`)

**Behaviour**

- Fetch each catalog URL; save bytes under `data/raw/{source_id}.html` or `.pdf`.
- If the raw file already exists, skip the network (replayable ingest).
- HTML → visible text (strip scripts/nav where practical).
- PDF → per-page text with `[Page N]` markers; warn and skip empty pages (no OCR in v1).
- Normalize whitespace.
- Write combined extracts to `data/raw/{source_id}.txt` for human inspection.
- Log character counts per source.

**Then you (or Cursor) inspect**

- Which sources are huge (complete factsheet, SID)?
- Are expense ratio / exit load / SIP / lock-in / riskometer / benchmark / statement download strings present?
- Is Large Cap / Bluechip visible in the complete factsheet extract?

**Do not:** chunk, embed, or open Chroma yet. If extraction is empty, fix the loader before Phase 3.

**Done when**

- Six `.txt` extracts exist in `data/raw/`.
- Console report of chars per `source_id`.
- Short inspection note (comment in load output or `data/raw/INSPECTION.md`): any empty pages, whether architecture chunk 700/120 still looks sane.

**Cursor prompt (copy)**

```
Implement Phase 2 only from Milestone-4/implementation.md.

Read Milestone-4/architecture.md §4.1.

Using src/catalog.py, implement src/load.py: cache downloads in data/raw/, extract HTML and PDF text, write per-source .txt, log empty PDF pages, print character counts. Reuse cache if files exist.

Do not chunk, embed, or use Chroma/Groq.

After a successful run, inspect the extracts and write data/raw/INSPECTION.md: counts, whether key facts appear, and whether chunk_size 700 / overlap 120 still fits. Stop at Phase 2 done.
```

---

## Phase 3 — Chunk + inspectable `chunks.txt`

**Goal:** Turn extracts into overlapping windows with metadata. Confirm strategy against real text.

**Create:** `src/chunk.py`

**Defaults (architecture §4.2)** — change only if INSPECTION.md justifies it, and update `architecture.md`:

- Recursive character split: `\n\n`, `\n`, `. `, space
- `chunk_size=700`, `chunk_overlap=120`
- Drop chunks shorter than 80 characters

**Metadata on every chunk:** `source_url`, `doc_type`, `title`, `scheme`, `page` (if PDF), `source_id`, `ingested_at` (ISO date).

**Scheme tagging:** catalog default for single-scheme docs. For `amc-factsheet-2025-04`, infer `flexicap` / `elss` / `largecap` from nearby headings (Bluechip, Large Cap, Flexi, ELSS, Tax Saver); else `general`.

**Output:** `data/processed/chunks.txt` — delimited records (id, metadata, full text) greppable by “expense ratio”, “lock-in”, etc.

Ids: `{source_id}-{chunk_index}`.

**Do not:** embed or write Chroma.

**Done when**

- `chunks.txt` exists and includes all six sources.
- Spot-check: ELSS lock-in and Investor Services “statement” language appear in some chunk.
- Document final size/overlap in a one-line header comment at the top of `chunks.txt`.

**Cursor prompt (copy)**

```
Implement Phase 3 only from Milestone-4/implementation.md.

Read Milestone-4/architecture.md §4.2 and data/raw/INSPECTION.md.

Implement src/chunk.py: recursive split 700/120 (unless inspection says otherwise — then update architecture.md), min 80 chars, full metadata, scheme tagging on the complete AMC factsheet. Write data/processed/chunks.txt.

Do not embed or use Chroma/Groq.

Grep chunks.txt for expense ratio, lock-in, and capital gains / statement. Report chunk counts per source_id. Stop at Phase 3 done.
```

---

## Phase 4 — Embed + Chroma persist (ingest job)

**Goal:** Ingestion pipeline end-to-end: Load → Chunk → Embed → Store. Run **once**.

**Create:** `src/ingest.py` (orchestrates load + chunk if needed, then embed/store)

**Behaviour**

- Embed **chunk text only** with `sentence-transformers/all-MiniLM-L6-v2`, 384-d, local.
- Persist Chroma at `data/chroma`, collection `mf_faq`, cosine space.
- Upsert by deterministic ids (re-ingest must not duplicate).
- Same encode settings you will reuse for queries (`normalize_embeddings` documented in code).
- CLI: `python -m src.ingest` (optional `--force` to rebuild).

**Do not:** build the chat UI or call Groq.

**Done when**

- `data/chroma` exists after one ingest.
- Collection count equals number of chunks in `chunks.txt`.
- Second ingest without `--force` is a no-op or upserts without doubling count.

**Cursor prompt (copy)**

```
Implement Phase 4 only from Milestone-4/implementation.md.

Read Milestone-4/architecture.md §4.3, §4.4, and §10.

Implement src/ingest.py: embed chunks with sentence-transformers/all-MiniLM-L6-v2 (local, 384-d), store in ChromaDB persist_directory data/chroma, collection mf_faq, deterministic ids. Do not ingest on a second run if the collection is already populated unless --force.

Do not add Groq, gates, or UI.

Run ingest once, print collection count vs chunks.txt count, and confirm a second run does not duplicate. Stop at Phase 4 done.
```

---

## Phase 5 — Retrieve (no LLM)

**Goal:** Question → embed → top_k chunks. Prove retrieval before generation.

**Create:** `src/retrieve.py`

**Behaviour**

- Load the **same** MiniLM model and encode flags as ingest.
- Query Chroma `top_k=5`.
- If the question names Flexi Cap / ELSS / Tax Saver / Large Cap / Bluechip, prefer matching `scheme` metadata (filter or rerank).
- Return text + metadata + scores.
- CLI: `python -m src.retrieve "What is the ELSS lock-in?"`

**Smoke queries (must retrieve a sensible `source_url`)**

1. Expense ratio of ICICI Prudential Flexi Cap
2. ELSS lock-in period
3. Minimum SIP (named scheme)
4. Exit load (named scheme)
5. Riskometer or benchmark (named scheme)
6. How to download capital-gains statement

**Done when**

- Each smoke query prints top chunk `source_url` / `scheme` / score.
- Statement question hits `investor-services` (or that URL).
- ELSS lock-in prefers `elss` docs, not a random Large Cap page.

**Cursor prompt (copy)**

```
Implement Phase 5 only from Milestone-4/implementation.md.

Read Milestone-4/architecture.md §5.2 and §5.3.

Implement src/retrieve.py: embed the question with the same MiniLM settings as ingest, Chroma top_k=5, optional scheme preference. CLI to print results.

Do not call Groq or build UI.

Run the six smoke queries listed in Phase 5 and report source_url and scheme for the top hit of each. Fix retrieval/metadata if scheme mixing is wrong. Stop at Phase 5 done.
```

---

## Phase 6 — Gates (PII, advice, returns)

**Goal:** Rule-based refusals **before** retrieve/LLM.

**Create:** `src/gates.py`

**PII:** PAN, Aadhaar, account-like numbers, OTP, email, phone. Do not write the raw message to disk. User-facing: personal identifiers are not needed; strip matches if anything is logged.

**Advice:** buy/sell/hold, “should I invest”, “which is better”, suitability, portfolio construction → refuse with polite facts-only copy + **one** official link (scheme page or Investor Services).

**Returns:** compute/compare performance/CAGR/returns ranking → do **not** calculate; short message + **one factsheet URL**.

Return a structured result the app can use: `{action: "refuse_advice"|"refuse_returns"|"strip_pii"|"allow", message?, citation_url?}`.

**Done when**

- Unit-style checks or a tiny `python -m src.gates` demo covering: “Should I buy Flexi Cap?”, “Which fund is better?”, “What was 5y return?”, a fake PAN, and a normal “What is the exit load of …?”.

**Cursor prompt (copy)**

```
Implement Phase 6 only from Milestone-4/implementation.md.

Read Milestone-4/PRD.md P3, P7, P8 and architecture.md §5.1.

Implement src/gates.py with rule-based PII, advice, and returns handling. No LLM. No chat logs of PII. Structured return value.

Add a small demo __main__ with the Phase 6 example inputs. Do not wire Streamlit yet. Stop at Phase 6 done.
```

---

## Phase 7 — Generate + answer formatter

**Goal:** Retrieved chunks → Groq → formatted answer. Citation and last-updated are **app-side**, not trusted from the model.

**Create:** `src/generate.py` (and a thin `src/pipeline.py` if useful: gates → retrieve → generate)

**Behaviour**

- Read `GROQ_API_KEY` from `.env`; model `llama-3.1-8b-instant` (overridable).
- System prompt: only use chunks; ≤3 sentences; no advice; no invented numbers; if missing, say so.
- User payload: question + numbered chunks with `source_url`, `scheme`, `page`.
- After the model returns, **overwrite** citation with top retrieved chunk `source_url` (or gate citation on refuse).
- `Last updated from sources:` = max `ingested_at` among retrieved chunks.
- Low similarity: do not invent facts; say not in indexed pages; still one catalog URL.
- Groq failure: user-visible error; **no** fallback to unsourced model knowledge.
- Query path must **not** fetch the live web.

**CLI:** `python -m src.pipeline "What is the ELSS lock-in?"` prints body + Source + last-updated.

**Done when**

- In-scope question: ≤3 sentence body, one URL from metadata, last-updated line.
- Advice question never hits Groq with a “recommendation” path (gate first).
- `.env` unused in git; no key in source.

**Cursor prompt (copy)**

```
Implement Phase 7 only from Milestone-4/implementation.md.

Read Milestone-4/architecture.md §5.1–§5.4 and §8.

Implement Groq generation plus app-side formatting (one Source URL from top chunk metadata, Last updated from sources). Wire gates → retrieve → generate in a CLI pipeline. Load key from .env. On Groq failure, error out without unsourced answers. Do not add Streamlit yet.

Demo one factual question and one advice question. Stop at Phase 7 done.
```

---

## Phase 8 — Tiny UI

**Goal:** Working prototype the PRD describes.

**Create:** `src/app.py` (Streamlit)

**Must show**

- Welcome: facts-only ICICI Prudential MF FAQ assistant
- Three example questions (clickable): Flexi Cap expense ratio; ELSS lock-in; download capital-gains statement
- Always-visible: “Facts-only. No investment advice.”
- Chat: user question → pipeline answer (body, Source URL, last-updated) or refusal layout
- If Chroma is missing: tell the user to run ingest; do not silently download

**Must not**

- Auth, accounts, or storing transcripts
- Auto-ingest on every page load

**Done when**

- `streamlit run src/app.py` works against existing `data/chroma`.
- Examples and disclaimer visible without asking.
- Restarting Streamlit does **not** re-embed the corpus.

**Cursor prompt (copy)**

```
Implement Phase 8 only from Milestone-4/implementation.md.

Read Milestone-4/PRD.md §7 and architecture.md §6 and §9.

Create src/app.py Streamlit UI: welcome, three example questions, disclaimer always visible, chat via the existing pipeline. If Chroma is empty, instruct to run ingest. Do not ingest on startup. Do not store chat or PII.

Keep the rest of the stack unchanged unless a small import fix is required. Stop at Phase 8 done.
```

---

## Phase 9 — End-to-end acceptance

**Goal:** Tick PRD §9 without new features.

**Checks**

| # | Check |
| --- | --- |
| 1 | Six sources ingested; chunks.txt inspectable; Chroma count matches. |
| 2 | App restart does not re-ingest. |
| 3 | Factual FAQs: short answer, **one** official citation, last-updated line. |
| 4 | Advice questions refused consistently. |
| 5 | Returns questions not calculated; factsheet link. |
| 6 | PII not stored; Groq key not in git (`git status` / `.gitignore`). |
| 7 | No third-party blogs as sources. |

Fix only bugs found. Do not expand corpus or add extra citations.

**Cursor prompt (copy)**

```
Execute Phase 9 only from Milestone-4/implementation.md.

Read Milestone-4/PRD.md §9.

Do not add features. Run through the Phase 9 checklist against the live pipeline/UI. Fix bugs that fail the checklist. Report pass/fail per item.
```

---

## Phase order (do not reorder)

```
0 Skeleton
    → 1 Catalog
        → 2 Load + inspect extracts
            → 3 Chunk + chunks.txt
                → 4 Embed + Chroma
                    → 5 Retrieve smoke tests
                        → 6 Gates
                            → 7 Groq + formatter
                                → 8 Streamlit
                                    → 9 Acceptance
```

**Suggested first message in a new Cursor chat for the next uncompleted phase:**

```
@Milestone-4/implementation.md @Milestone-4/architecture.md
Implement only Phase N. Do not start Phase N+1.
```
