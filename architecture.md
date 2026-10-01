# Architecture

**Product:** Mutual Fund FAQ Assistant (facts-only RAG chatbot)  
**Source of truth:** [PRD.md](./PRD.md)  
**Last updated:** 2026-10-01

This document describes how the prototype implements **full RAG**: ingestion (once, persisted) and retrieval/generation (every question). It is not a prompt-only chatbot.

---

## 1. Design goals

| Goal | Architectural implication |
| --- | --- |
| Answers only from official corpus | Generation is grounded in retrieved chunks; no web search at query time. |
| One citation per answer | Citation URL is taken from retrieved chunk metadata, not invented by the LLM. |
| Facts-only, no advice | A query gate refuses buy/sell/portfolio/returns-computation intents before generation, or the LLM is constrained to refuse with a fixed educational link. |
| Restart without re-ingest | ChromaDB on disk; ingest is a separate job. |
| Inspectable corpus | All chunks written to a readable `.txt` file. |
| No PII stored | Chat is in-memory; no logging of PAN/Aadhaar/account/OTP/email/phone. |
| Local embeddings, Groq for LLM | Same MiniLM model for documents and queries; Groq key only in `.env`. |

---

## 2. High-level system

```
                    ┌─────────────────────────────────────┐
                    │           Tiny chat UI              │
                    │  welcome · 3 examples · disclaimer  │
                    └─────────────────┬───────────────────┘
                                      │ question
                                      ▼
                    ┌─────────────────────────────────────┐
                    │           Query service             │
                    │  PII strip · intent gate · embed    │
                    │  retrieve · Groq · format answer    │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────┴───────────────────┐
                    ▼                                     ▼
         ┌──────────────────┐                  ┌──────────────────┐
         │ ChromaDB (disk)  │                  │ Groq LLM (API)   │
         │ 384-d MiniLM     │                  │ generation only  │
         └────────▲─────────┘                  └──────────────────┘
                  │ persist (once)
         ┌────────┴─────────┐
         │ Ingestion job    │
         │ Load→Chunk→Embed │
         └────────▲─────────┘
                  │
         ┌────────┴─────────┐
         │ 6 official pages │
         │ HTML + PDFs      │
         └──────────────────┘
```

Two runtimes:

1. **Ingest job** — load public sources, chunk, embed, write `chunks.txt`, upsert ChromaDB.
2. **App** — serve UI; on each question embed → retrieve → generate → display.

---

## 3. Logical components

| Component | Responsibility |
| --- | --- |
| Source catalog | Fixed list of the six PRD URLs plus `doc_type`, default `scheme`, and `title`. |
| Loaders | HTML → visible text; PDF → page-aware text. Strip nav/boilerplate where possible. |
| Chunker | Recursive character split with overlap; attach metadata; dump `.txt`. |
| Embedder | `sentence-transformers/all-MiniLM-L6-v2` (384-d), used for **chunks and queries**. |
| Vector store | ChromaDB collection, persist directory on disk. |
| Retriever | Embed question, `top_k` similarity search, optional scheme hint from the question. |
| Intent / PII gate | Detect advice, returns-comparison, and PII patterns. |
| Generator | Groq chat completion with retrieved context; enforce ≤3 sentences + citation + last-updated. |
| UI | Welcome, three example questions, disclaimer, Q&A thread. |

---

## 4. Ingestion pipeline

```
Load → Chunk → Embed → Store
```

Run **once** (or when sources are refreshed). App startup **skips** ingest if the persist directory already has a collection.

### 4.1 Load

| Source | Format | Loader | Notes |
| --- | --- | --- | --- |
| Flexicap scheme page | HTML | HTTP GET + HTML-to-text | Scheme-specific marketing/facts. |
| Flexi Cap factsheet | PDF | PDF extract per page | Dense tables (TER, load, SIP). |
| ELSS Tax Saver factsheet | PDF | PDF extract per page | Same layout family as Flexi Cap. |
| ELSS SID (AMFI) | PDF | PDF extract per page | Long legal SID; lock-in, loads, investment limits. |
| Complete AMC factsheet Apr 2025 | PDF | PDF extract per page | **Multi-scheme**; must tag scheme (esp. Large Cap / Bluechip). |
| Investor Services | HTML | HTTP GET + HTML-to-text | Statement / capital gains / STT how-to. |

Raw extracts may be cached under `data/raw/` so ingest can be replayed without re-downloading.

**Normalization:** collapse excess whitespace; keep page breaks as markers (`[Page N]`) for PDF metadata; do not OCR-dependent image-only pages in v1 (log a warning if a page is empty).

### 4.2 Chunk (proposed strategy)

This proposal is based on document *types* in the PRD (factsheets, SID, HTML). Confirm on first extract; if pages are mostly 1–2 sentence table cells or huge SID paragraphs, adjust size before locking code.

**Why this data needs medium overlapping windows**

- Factsheets mix **label + value** (expense ratio, exit load, min SIP, riskometer, benchmark) in tables. Too-small chunks lose the scheme name; too-large chunks mix several schemes in the complete factsheet.
- SID sections are long; a window with overlap keeps a heading attached to the following rule (e.g. ELSS 3-year lock-in).
- HTML service pages are procedural (“how to download…”); a chunk should hold a full step sequence.
- **MiniLM-L6-v2 max sequence length is 256 tokens.** Chunks must stay under that so embeddings are not silently truncated.

**Parameters**

| Parameter | Value | Rationale |
| --- | --- | --- |
| Splitter | Recursive character (`\n\n`, `\n`, `. `, ` `) | Respects paragraphs/pages before mid-sentence cuts. |
| `chunk_size` | **700 characters** | ~175–220 tokens; under 256-token MiniLM limit; enough for a factsheet block or a SID subsection. |
| `chunk_overlap` | **120 characters** | Carries table headers / section titles into the next window. |
| Min chunk | Drop fragments &lt; 80 characters | Avoids nav crumbs and page numbers as standalone vectors. |

**Per-chunk metadata (all required except `page`)**

| Field | Purpose |
| --- | --- |
| `source_url` | The **single citation** shown to the user. |
| `doc_type` | `scheme_page` \| `factsheet` \| `sid` \| `investor_services` |
| `title` | Human label from the catalog. |
| `scheme` | `flexicap` \| `elss` \| `largecap` \| `general` |
| `page` | PDF page number if known. |
| `source_id` | Stable id (`flexicap-html`, `elss-sid`, …). |
| `ingested_at` | ISO date used for “Last updated from sources:”. |

**Scheme tagging**

- Catalog default for single-scheme docs (Flexi Cap page/PDF, ELSS factsheet/SID).
- Complete AMC factsheet: infer `scheme` from nearby headings (`Bluechip` / `Large Cap` / `Flexi` / `ELSS` / `Tax Saver`); if unknown, `general`.
- Investor services: `general`.

**Inspectable artifact**

- Path: `data/processed/chunks.txt`
- Format: one record per chunk, delimited, including id, metadata, and full text so reviewers can grep expense ratio / lock-in without opening Chroma.

### 4.3 Embed

- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Vectors: **384 dimensions**
- Input: chunk text only (metadata is stored alongside, not concatenated into the vector unless a short prefix `scheme=` helps retrieval — default **no prefix** in v1; add later if scheme confusion appears).
- Device: local CPU/GPU; **no embedding API key**.

### 4.4 Store

- Engine: **ChromaDB** with `persist_directory` (e.g. `data/chroma`).
- Collection: `mf_faq` (or similar), cosine space matching MiniLM.
- Id: deterministic (`{source_id}-{chunk_index}`) so re-ingest upserts instead of duplicating.
- **Do not** embed or ingest on every app restart if the collection exists and is non-empty.

---

## 5. Query pipeline

```
Question → Embed → Retrieve top chunks → LLM → Answer
```

### 5.1 Pre-process

1. **PII:** If the message matches PAN / Aadhaar / account / OTP / email / phone patterns, do **not** write it to disk. Reply that personal identifiers are not needed; strip matches before any optional debug log.
2. **Intent gate (rules first):**
   - Advice / suitability / buy-sell-hold / “which is better” → **refuse** (P3).
   - Compute or compare **returns / performance** → **do not calculate**; short message + **one factsheet URL** (P7).
   - In-scope factual FAQ → continue to retrieve.

Refusal template: polite facts-only sentence + one educational/official link (Investor Services or the relevant scheme page). No generated portfolio commentary.

### 5.2 Embed question

Same MiniLM model and normalization as ingestion (identical encode settings: same `normalize_embeddings` flag).

### 5.3 Retrieve

| Parameter | Value |
| --- | --- |
| `top_k` | **5** |
| Metric | Cosine similarity on 384-d vectors |
| Optional filter | If the question names a scheme, Chroma `where` on `scheme` **or** retrieve then prefer matching `scheme` metadata. |

Use the **highest-scoring chunk’s `source_url`** as the single citation (P2). If several chunks tie and disagree, still emit **one** URL (best score); do not list multiple sources in v1.

When the question names Flexi Cap or ELSS, **prefer dedicated scheme pages** (`flexicap-html` / `flexicap-factsheet`, `elss-factsheet` / `elss-sid`) over mixed pages from the complete AMC factsheet. Rerank those hits if they contain the asked fact (lock-in, TER, SIP, exit load, NAV).

If scores are all very low, still answer “not in the official pages we indexed” and cite the closest catalog URL (scheme page or Investor Services), rather than hallucinating numbers.

### 5.4 Generate (Groq)

- Provider: **Groq**; `GROQ_API_KEY` in `.env` only (gitignored).
- Suggested model: `llama-3.1-8b-instant` (short factual answers; swap via env if needed).
- Context: concatenated top chunks with `source_url` / `scheme` / `page` headers.
- System rules:
  - Use **only** provided chunks.
  - **≤ 3 sentences** of body.
  - No advice, no return math, no invented TER/load/SIP figures.
  - If chunks conflict or lack the fact, say the fact is not in the retrieved excerpts.

**App-side formatting (do not trust the model alone):**

```
<answer body>
Source: <source_url from top chunk>
Last updated from sources: <max ingested_at among retrieved chunks>
```

---

## 6. Application and UX mapping

| PRD UX | Implementation |
| --- | --- |
| Welcome line | Static copy: facts-only ICICI Prudential MF FAQ assistant. |
| 3 example questions | e.g. Flexi Cap expense ratio; ELSS lock-in; how to download capital-gains statement. |
| Disclaimer | Always visible: “Facts-only. No investment advice.” |
| Answer layout | Body → one URL → last-updated line. |
| Refusal layout | Fixed polite copy + one official/educational URL. |

Suggested UI: **Streamlit** (or equivalent) single page — enough for the tiny prototype; no auth, no user accounts.

---

## 7. Suggested repository layout

```
Milestone-4/
  PRD.md
  architecture.md
  Docs
  .env                 # GROQ_API_KEY; never commit
  .gitignore
  requirements.txt
  data/
    raw/               # downloaded HTML/PDF (optional cache)
    processed/
      chunks.txt       # inspectable chunks
    chroma/            # Chroma persist directory
  src/
    catalog.py         # six sources + metadata defaults
    load.py
    chunk.py
    ingest.py          # Load → Chunk → Embed → Store
    retrieve.py
    generate.py
    gates.py           # PII + advice/returns
    app.py             # UI
```

---

## 8. Security and privacy

| Topic | Rule |
| --- | --- |
| Secrets | `.env` + `.gitignore`; never commit Groq key. |
| PII | No accept/store of PAN, Aadhaar, account numbers, OTPs, emails, phones; no chat transcript DB. |
| Sources | Only the six official URLs; no third-party blogs. |
| Network | Ingest may fetch AMC/AMFI; query path does not browse the live web for new facts. |

---

## 9. Failure modes

| Failure | Behaviour |
| --- | --- |
| Empty/failed PDF page | Skip with log; remaining corpus still serves. |
| Chroma missing on startup | Message to run ingest; do not silently download if product owner prefers offline. |
| Groq down | Surface a user-visible error; do not fall back to unsourced model knowledge. |
| Ambiguous multi-scheme retrieve | Prefer metadata `scheme` match; never merge TER from two schemes into one number. |

---

## 10. Implementation sequence

1. Catalog the six URLs and download/extract text; **inspect** length, tables, and scheme mixing.
2. Confirm or tweak chunk size/overlap; write `chunks.txt`.
3. Embed + persist ChromaDB; verify a few FAQ queries return the right `source_url`.
4. Wire Groq + gates + answer formatter.
5. Tiny UI with welcome, three examples, disclaimer.

Chunk parameters in §4.2 are the default to implement unless inspection of `data/raw/` shows systematic truncation or scheme bleed — then update this file and re-ingest.
