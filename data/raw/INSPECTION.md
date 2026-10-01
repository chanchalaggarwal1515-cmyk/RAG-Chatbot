# Phase 2 inspection

Inspected after `python -m src.load` on 2026-10-01. Cached PDFs reused; HTML re-rendered with Playwright because the AMC site is a React SPA (`#root` empty in static GET).

## Character counts

| source_id | chars | notes |
| --- | ---: | --- |
| flexicap-html | 4,885 | Rendered scheme page. Fund-metric cards clip TER/exit load with `...`; full sentences are on the Flexi Cap factsheet. |
| flexicap-factsheet | 9,633 | Dense 1–2 page factsheet; tables extract as broken lines. |
| elss-factsheet | 9,888 | Same layout family as Flexi Cap. |
| elss-sid | 224,783 | Long SID; lock-in is a dedicated section. |
| amc-factsheet-2025-04 | 863,304 | Largest file. Mixes many schemes. **Page 1 empty** (cover/image, no OCR). |
| investor-services | 9,195 | Bare catalog URL `.../investor-services` **404s** for HTTP clients. Loader rendered official child pages under that path (statements hub, capital-gain, account-statement, pre-login capital-gain). Citation URL in the catalog is unchanged. |

## Empty / noisy pages

- `amc-factsheet-2025-04.pdf` page 1: empty, skipped (logged). Remaining pages extracted.
- Factsheet PDFs: headers/footers and table columns interleave; label+value often still in the same ~700-character window.
- Flexi Cap HTML: some metric values truncated in the live DOM; do not treat those ellipses as source of truth.

## Key facts present?

| Topic | Where it showed up |
| --- | --- |
| Expense ratio / TER | Flexi Cap factsheet: Base Expense Ratio Other 1.37% / Direct 0.65%. HTML has TER but clipped. ELSS factsheet has Base Expense Ratio lines. |
| Exit load | Flexi Cap factsheet: 1% if redeemed within one month, else NIL. HTML has Exit Load heading. ELSS factsheet: Nil (lumpsum & SIP/STP). |
| Minimum SIP | Flexi Cap HTML: Installment Amount (Min ₹100); SIP Rs. 100 monthly / Rs. 5,000 quarterly. Factsheets point to annexure for SIP details. |
| ELSS lock-in | SID: statutory **3 years** from allotment (section XXII). Also on SID cover. |
| Riskometer / benchmark | Flexi Cap: BSE 500 TRI, very high risk. ELSS: Nifty 500 TRI. |
| Capital gains / statements | Investor Services: Account Statement, Capital Gains Statement, STT Statement, GET STATEMENT; capital-gain page describes STCG/LTCG on redemptions and switches. |
| Large Cap / Bluechip | Complete AMC factsheet TOC and scheme pages: **ICICI Prudential Bluechip Fund** / Large Cap Fund. |

## Chunk size 700 / overlap 120

**Keep architecture defaults.**

- MiniLM-L6-v2 256-token cap still applies.
- Factsheets are short (~10k chars) with label+value pairs; 700/120 should keep TER, exit load, and riskometer with the scheme name.
- SID paragraphs are long; overlap should carry “LOCK-IN PERIOD” into the 3-year rule.
- Complete factsheet is huge and multi-scheme — tagging `scheme` in Phase 3 matters more than shrinking chunks.
- HTML service steps fit in one 700-char window per statement type.

No change to `chunk_size` / `chunk_overlap` before Phase 3.
