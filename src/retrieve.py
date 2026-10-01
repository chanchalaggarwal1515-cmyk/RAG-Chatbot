"""Question → embed → retrieve top chunks. No LLM."""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any, TypedDict

from src.embedder import embed_texts
from src.ingest import get_collection

TOP_K = 5
CANDIDATE_K = 40

# Named-scheme questions should read these docs, not the mixed complete AMC factsheet.
DEDICATED_SOURCES: dict[str, tuple[str, ...]] = {
    "flexicap": ("flexicap-html", "flexicap-factsheet"),
    "elss": ("elss-factsheet", "elss-sid"),
    "largecap": ("amc-factsheet-2025-04",),
}

SCHEME_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("flexicap", re.compile(r"flexi\s*cap|flexicap", re.I)),
    ("elss", re.compile(r"\belss\b|tax\s*saver", re.I)),
    ("largecap", re.compile(r"blue\s*chip|bluechip|\blarge\s*cap\b", re.I)),
]

FACT_TERMS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (
        re.compile(r"lock[\s-]*in", re.I),
        ("statutory lock in of 3 years", "statutory lock in", "lock-in period of 3 years", "lock in of 3 years"),
    ),
    (re.compile(r"expense|ter\b", re.I), ("expense ratio", "total expense", "ipff:", "base expense ratio")),
    (re.compile(r"exit\s*load", re.I), ("exit load", "1% of the applicable nav")),
    (re.compile(r"\bsip\b|minimum\s+install", re.I), ("sip", "minimum installments", "monthly sip : rs. 100")),
    (re.compile(r"riskometer|very high risk", re.I), ("riskometer", "very high risk")),
    (re.compile(r"benchmark", re.I), ("benchmark", "bse 500", "nifty 500")),
    (re.compile(r"\bnav\b|current value|per unit", re.I), ("nav (rs.) per unit", "nav (as on", "per unit")),
]

STATEMENT_RE = re.compile(
    r"capital\s*gains?|account\s*statement|\bstt\b|download\s+.*statement|how to download",
    re.I,
)


class Hit(TypedDict):
    id: str
    text: str
    source_url: str
    scheme: str
    source_id: str
    doc_type: str
    title: str
    page: int | None
    ingested_at: str
    distance: float
    score: float


def detect_scheme(question: str) -> str | None:
    for scheme, pattern in SCHEME_PATTERNS:
        if pattern.search(question):
            return scheme
    return None


def wants_statements(question: str) -> bool:
    return bool(STATEMENT_RE.search(question))


def _to_hit(chunk_id: str, document: str, metadata: dict[str, Any], distance: float) -> Hit:
    page = metadata.get("page")
    return {
        "id": chunk_id,
        "text": document,
        "source_url": str(metadata.get("source_url", "")),
        "scheme": str(metadata.get("scheme", "general")),
        "source_id": str(metadata.get("source_id", "")),
        "doc_type": str(metadata.get("doc_type", "")),
        "title": str(metadata.get("title", "")),
        "page": int(page) if page not in (None, "") else None,
        "ingested_at": str(metadata.get("ingested_at", "")),
        "distance": float(distance),
        "score": 1.0 - float(distance),
    }


def _fact_bonus(question: str, text: str) -> int:
    lowered = text.lower()
    bonus = 0
    for pattern, needles in FACT_TERMS:
        if pattern.search(question):
            bonus += sum(3 for needle in needles if needle in lowered)
    return bonus


def _source_rank(hit: Hit, question: str) -> tuple[int, int, int, float]:
    """Lower tuple sorts first: dedicated doc, fact keywords, then embedding distance."""
    scheme = detect_scheme(question)
    dedicated = DEDICATED_SOURCES.get(scheme or "", ())
    statements = wants_statements(question)
    if statements:
        dedicated_hit = 0 if hit["source_id"] == "investor-services" else 1
    elif dedicated:
        dedicated_hit = 0 if hit["source_id"] in dedicated else 1
    elif scheme:
        dedicated_hit = 0 if hit["scheme"] == scheme else 1
    else:
        dedicated_hit = 0 if hit["source_id"] != "amc-factsheet-2025-04" else 1
    fact = -_fact_bonus(question, hit["text"])
    page_pref = 0
    if re.search(r"expense|ter\b|exit\s*load|sip", question, re.I) and hit["doc_type"] == "scheme_page":
        page_pref = -1
    return (dedicated_hit, fact, page_pref, hit["distance"])


def _prefer(hits: list[Hit], question: str, top_k: int = TOP_K) -> list[Hit]:
    ordered = sorted(hits, key=lambda hit: _source_rank(hit, question))
    return ordered[:top_k]


def _merge_hits(hits: list[Hit], extra: list[Hit]) -> list[Hit]:
    seen = {hit["id"] for hit in hits}
    merged = list(hits)
    for hit in extra:
        if hit["id"] not in seen:
            merged.append(hit)
            seen.add(hit["id"])
    return merged


def _query_hits(
    collection: Any,
    embedding: list[float],
    n_results: int,
    where: dict[str, Any] | None = None,
    where_document: dict[str, Any] | None = None,
) -> list[Hit]:
    kwargs: dict[str, Any] = {
        "query_embeddings": [embedding],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    if where_document:
        kwargs["where_document"] = where_document
    try:
        return _hits_from_query(collection.query(**kwargs))
    except Exception:
        if where_document:
            kwargs.pop("where_document", None)
            return _hits_from_query(collection.query(**kwargs))
        raise


def _scan_keyword_hits(collection: Any, source_ids: tuple[str, ...] | list[str], question: str) -> list[Hit]:
    needles: list[str] = []
    for pattern, terms in FACT_TERMS:
        if pattern.search(question):
            needles.extend(terms)
    if not needles:
        return []
    data = collection.get(
        where={"source_id": {"$in": list(source_ids)}},
        include=["documents", "metadatas"],
    )
    ids = data.get("ids") or []
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []
    found: list[Hit] = []
    for chunk_id, doc, meta in zip(ids, docs, metas):
        text = doc or ""
        lowered = text.lower()
        if any(needle in lowered for needle in needles):
            found.append(_to_hit(chunk_id, text, dict(meta or {}), 0.05))
    found.sort(key=lambda hit: -_fact_bonus(question, hit["text"]))
    return found[:10]


def retrieve(question: str, top_k: int = TOP_K) -> list[Hit]:
    if not question.strip():
        raise ValueError("question is empty")
    collection = get_collection()
    if collection.count() == 0:
        raise RuntimeError("Chroma collection is empty. Run: python -m src.ingest")

    embedding = embed_texts([question.strip()])[0]
    n_results = min(max(top_k, CANDIDATE_K), collection.count())
    hits = _query_hits(collection, embedding, n_results)

    scheme = detect_scheme(question)
    dedicated = DEDICATED_SOURCES.get(scheme or "", ())
    source_ids: tuple[str, ...] | list[str]
    if wants_statements(question):
        source_ids = ("investor-services",)
    elif dedicated:
        source_ids = dedicated
    else:
        source_ids = ()

    if source_ids:
        where = {"source_id": {"$in": list(source_ids)}}
        hits = _merge_hits(hits, _query_hits(collection, embedding, min(n_results, 20), where=where))
        hits = _merge_hits(hits, _scan_keyword_hits(collection, source_ids, question))

    return _prefer(hits, question, top_k=top_k)


def _hits_from_query(result: dict[str, Any]) -> list[Hit]:
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    return [
        _to_hit(chunk_id, doc or "", dict(meta or {}), dist)
        for chunk_id, doc, meta, dist in zip(ids, docs, metas, distances)
    ]


SMOKE_QUERIES = [
    "Expense ratio of ICICI Prudential Flexi Cap",
    "ELSS lock-in period",
    "Minimum SIP of ICICI Prudential Flexi Cap Fund",
    "Exit load of ICICI Prudential Flexi Cap Fund",
    "Riskometer or benchmark of ICICI Prudential Flexi Cap",
    "How to download capital-gains statement",
]


def print_hits(question: str, hits: list[Hit]) -> None:
    print(f"Q: {question}")
    if not hits:
        print("  (no hits)")
        return
    for i, hit in enumerate(hits, start=1):
        print(
            f"  {i}. score={hit['score']:.4f} scheme={hit['scheme']} "
            f"source_id={hit['source_id']} url={hit['source_url']}"
        )
        preview = " ".join(hit["text"].split())[:160].encode("ascii", "replace").decode("ascii")
        print(f"     {preview}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve top chunks for a question")
    parser.add_argument("question", nargs="*", help="User question")
    parser.add_argument("--smoke", action="store_true", help="Run the six Phase 5 smoke queries")
    args = parser.parse_args()

    if args.smoke:
        for query in SMOKE_QUERIES:
            print_hits(query, retrieve(query))
            print()
        return

    question = " ".join(args.question).strip()
    if not question:
        parser.error('pass a question, e.g. python -m src.retrieve "What is the ELSS lock-in?"')
    print_hits(question, retrieve(question))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
