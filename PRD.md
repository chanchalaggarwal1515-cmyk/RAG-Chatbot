# Product Requirements Document (PRD)

**Product:** Mutual Fund FAQ Assistant (Facts-Only RAG Chatbot)  
**Milestone:** 4  
**Status:** Draft  
**Last updated:** 2026-10-01

---

## 1. Overview

Build a small FAQ assistant that answers **factual questions only** about selected ICICI Prudential Mutual Fund schemes (expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, how to download statements) using **official public pages**. Every answer must include **one source link**. The product must not give investment advice.

The assistant is implemented as a **RAG (Retrieval-Augmented Generation)** chatbot that answers using **only the provided source corpus**. Architecture must follow the full RAG stages: **data ingestion** and **data retrieval**.

---

## 2. Problem

Retail investors and internal support/content teams repeatedly ask the same scheme-level facts. Answers are scattered across AMC factsheets, SIDs, and investor-service pages. Unofficial blogs and screenshots are unreliable and out of policy.

Users need a fast, citable, facts-only interface that never stores PII and never recommends buy/sell/hold.

---

## 3. Goals and non-goals

### 3.1 Goals

- Answer factual queries about the scoped ICICI Prudential schemes from official public sources.
- Show **exactly one clear citation URL** on every answer.
- Refuse opinionated or portfolio questions politely; stay facts-only and link to a relevant educational/official page.
- Ingest sources once into a persisted vector store; retrieve relevant chunks at query time; generate short, sourced answers.
- Keep a tiny UI: welcome line, three example questions, and the disclaimer **“Facts-only. No investment advice.”**

### 3.2 Non-goals

- Investment advice, suitability, or “should I buy/sell?” recommendations.
- Computing or comparing returns / performance claims (if asked, point to the official factsheet).
- Accepting or storing PII (PAN, Aadhaar, account numbers, OTPs, emails, phone numbers).
- Third-party blogs, app back-end screenshots, or unofficial aggregators as sources.
- Broad AMC coverage beyond the chosen 3–5 schemes and the six listed public pages for this milestone.

---

## 4. Users

| Persona | Need |
| --- | --- |
| Retail user comparing schemes | Quick factual lookups (fees, lock-in, SIP minimum, riskometer, benchmark, statements) with a source they can verify. |
| Support / content team | Repeatable, citable answers to the same MF FAQ without drafting from memory. |

---

## 5. Scope

### 5.1 Corpus (AMC and schemes)

- **AMC:** ICICI Prudential Asset Management Company.
- **Schemes (minimum 3, target 3–5):** include at least **Flexi Cap**, **ELSS (Tax Saver)**, and **Large Cap / Bluechip** (via the complete AMC factsheet).

### 5.2 Official source pages (6)

| # | Source | URL |
| --- | --- | --- |
| 1 | ICICI Pru Flexicap Fund scheme page | https://www.icicipruamc.com/mutual-fund/equity-funds/icici-prudential-flexicap-fund/1822 |
| 2 | Flexi Cap Fund factsheet (PDF) | https://www.icicipruamc.com/blob/knowledgecentre/factsheet-schemes/Schemes/1.%20Equity%20Schemes/ICICI%20Prudential%20Flexi%20Cap%20Fund.pdf |
| 3 | ELSS Tax Saver Fund factsheet (PDF) | https://www.icicipruamc.com/blob/knowledgecentre/factsheet-schemes/Schemes/1.%20Equity%20Schemes/ICICI%20Prudential%20ELSS%20-%20Tax%20Saver%20Fund.pdf |
| 4 | ELSS Tax Saver Fund SID (AMFI) | https://portal.amfiindia.com/spages/131.pdf |
| 5 | Complete AMC factsheet, April 2025 (includes Large Cap / Bluechip) | https://www.icicipruamc.com/blob/downloads/Files/Historic%20Factsheets/2025-2026/Complete%20Factsheet%20April%202025.pdf |
| 6 | Investor Services (account, capital gains, STT statements) | https://www.icicipruamc.com/investor-services |

Public sources only: AMC / SEBI / AMFI factsheets, KIM/SID, scheme FAQs, fee/charges pages, riskometer/benchmark notes, statement/tax-doc guides.

### 5.3 Question types in scope

- Expense ratio of a scoped scheme.
- ELSS lock-in.
- Minimum SIP.
- Exit load.
- Riskometer / benchmark.
- How to download capital-gains (and related) statements.

### 5.4 Out of scope questions

- Buy/sell/hold, portfolio construction, “which fund is better.”
- Personalized tax or account troubleshooting that needs PII.
- Performance ranking, return calculations, or unofficial market commentary.

---

## 6. Product requirements

### 6.1 FAQ assistant (working prototype)

| ID | Requirement | Priority |
| --- | --- | --- |
| P1 | Answers are factual and grounded in retrieved corpus chunks only. | Must |
| P2 | Every answer includes **one** clear citation link to an official source. | Must |
| P3 | Opinionated / portfolio questions are refused with a polite facts-only message plus a relevant educational/official link. | Must |
| P4 | UI: welcome line + **3 example questions** + note: “Facts-only. No investment advice.” | Must |
| P5 | Answers are **≤ 3 sentences**. | Must |
| P6 | Each answer includes **“Last updated from sources: &lt;date&gt;”**. | Must |
| P7 | Do not compute or compare returns; if asked, link to the official factsheet. | Must |
| P8 | Do not accept or store PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers. | Must |

### 6.2 RAG architecture (required stages)

The system must implement **all RAG stages**, not a prompt-only chatbot.

**Ingestion (run once, persist):**

```
Load → Chunk → Embed → Store in Vector DB
```

**Query (every question):**

```
Question → Embed → Retrieve top chunks → LLM → Answer
```

| Stage | Requirement |
| --- | --- |
| Load | Ingest the six official pages/PDFs into text suitable for chunking. |
| Chunk | Agent inspects the data **before writing code**, proposes a strategy (why it fits this corpus), and specifies **chunk size, overlap, and per-chunk metadata**. Persist **all chunks** to a readable `.txt` file for inspection. |
| Embed | Use **the same model** for document chunks and the user question: `sentence-transformers/all-MiniLM-L6-v2` (local, no API key, **384-dimension** vectors). |
| Store | **ChromaDB**, persisted to disk so ingestion is not re-run on every restart. |
| Retrieve | Embed the question; retrieve top relevant chunks from ChromaDB. |
| Generate | **Groq** LLM; API key in `.env`, **never committed to Git**. Answer using retrieved chunks only. |

---

## 7. UX requirements

- **Welcome:** One short line stating this is a facts-only ICICI Prudential MF FAQ assistant.
- **Examples:** Three clickable/suggested questions covering different schemes or topics (e.g. expense ratio, ELSS lock-in, statement download).
- **Disclaimer always visible:** “Facts-only. No investment advice.”
- **Answer layout:** Body (≤ 3 sentences) → citation URL → “Last updated from sources: …”
- **Refusal layout:** Polite refusal → no advice → one educational/official link.
- **PII:** If the user pastes identifiers, do not persist them; remind that the assistant does not need personal details.

---

## 8. Technical constraints

| Item | Constraint |
| --- | --- |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` (local, 384-d) |
| Vector DB | ChromaDB, on-disk persistence |
| LLM | Groq; key via `.env` only |
| Secrets | `.env` gitignored; never commit API keys |
| Chunk artifacts | Human-readable `.txt` of all chunks |
| Sources | Official AMC/SEBI/AMFI public pages listed in §5.2 |
| Runtime | Embeddings run locally; Groq used only for generation |

---

## 9. Success criteria

The prototype is done when:

1. All six sources are ingested, chunked (strategy documented), embedded, and stored in persisted ChromaDB.
2. Chunks are inspectable in a `.txt` file.
3. A user can ask in-scope FAQs and receive a short, facts-only answer with **one** official citation and a last-updated line.
4. Out-of-scope advice questions are refused consistently.
5. Restarting the app does **not** require re-ingestion if the vector store exists on disk.
6. No PII is stored; Groq key is not in git.

---

## 10. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| PDF/HTML extraction is noisy (tables, headers, footers). | Inspect extracted text; choose chunk size/overlap and metadata (scheme, source URL, doc type, page) accordingly. |
| LLM hallucinates beyond retrieved text. | System prompt: answer only from chunks; if insufficient, say so and still cite the closest official page. |
| Advice-seeking prompts. | Explicit refusal policy + educational link. |
| Stale fees/loads vs. live AMC site. | Show last-updated from sources; do not invent newer numbers. |
| Large complete factsheet mixes many schemes. | Metadata must tag scheme name so retrieval stays on the asked scheme. |

---

## 11. Open decisions (for implementation, pre-code)

Before writing ingestion code, the implementation agent must inspect the loaded documents and record:

- Chunk size and overlap.
- Why that strategy fits factsheets / SID / HTML service pages.
- Metadata fields on each chunk (at minimum: `source_url`, `title`/`doc_type`, `scheme` if known).
- Path of the inspectable chunks `.txt` file.

These decisions belong in the architecture/implementation notes, not as silent defaults.
