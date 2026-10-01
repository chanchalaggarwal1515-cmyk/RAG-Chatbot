"""Chunk official extracts for embedding.

Defaults from architecture §4.2 and data/raw/INSPECTION.md: 700 / 120 / min 80.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import TypedDict

from src.catalog import SOURCES, Scheme, Source
from src.load import ROOT, read_extracts

CHUNK_SIZE = 700
CHUNK_OVERLAP = 120
MIN_CHUNK = 80
SEPARATORS = ["\n\n", "\n", ". ", " "]

PROCESSED_DIR = ROOT / "data" / "processed"
CHUNKS_PATH = PROCESSED_DIR / "chunks.txt"

PAGE_RE = re.compile(r"\[Page (\d+)\]")

# Ordered so the last heading before a chunk wins. US Bluechip is excluded
# by requiring "Prudential Bluechip Fund" with no "US" in between.
AMC_HEADINGS: list[tuple[re.Pattern[str], Scheme]] = [
    (re.compile(r"ICICI Prudential Flexi\s*Cap Fund|ICICI Prudential Flexicap Fund", re.I), "flexicap"),
    (re.compile(r"ICICI Prudential ELSS.{0,40}Tax Saver Fund|ICICI Prudential Long Term Equity Fund \(Tax Saving\)", re.I), "elss"),
    (re.compile(r"ICICI Prudential Bluechip Fund", re.I), "largecap"),
]


class Chunk(TypedDict):
    id: str
    text: str
    source_url: str
    doc_type: str
    title: str
    scheme: str
    source_id: str
    ingested_at: str
    page: int | None


def recursive_split(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Windows of at most chunk_size characters, overlapped, split on separators."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        if end < n:
            window = text[start:end]
            cut = -1
            for sep in SEPARATORS:
                pos = window.rfind(sep)
                if pos >= chunk_size // 4:
                    cut = max(cut, pos + len(sep))
            if cut > 0:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def _page_at(text: str, offset: int) -> int | None:
    last: int | None = None
    for match in PAGE_RE.finditer(text):
        if match.start() <= offset:
            last = int(match.group(1))
        else:
            break
    return last


def _scheme_spans(text: str) -> list[tuple[int, Scheme]]:
    hits: list[tuple[int, Scheme]] = []
    for pattern, scheme in AMC_HEADINGS:
        for match in pattern.finditer(text):
            hits.append((match.start(), scheme))
    hits.sort(key=lambda item: item[0])
    return hits


def _scheme_at(spans: list[tuple[int, Scheme]], offset: int, default: Scheme) -> Scheme:
    current: Scheme = default
    for start, scheme in spans:
        if start <= offset:
            current = scheme
        else:
            break
    return current


def chunks_for_source(source: Source, text: str, ingested_at: str) -> list[Chunk]:
    windows = recursive_split(text)
    spans = _scheme_spans(text) if source["source_id"] == "amc-factsheet-2025-04" else []
    chunks: list[Chunk] = []
    search_from = 0
    index = 0
    for window in windows:
        stripped = window.strip()
        if len(stripped) < MIN_CHUNK:
            continue
        offset = text.find(window[:80], search_from)
        if offset < 0:
            offset = search_from
        search_from = max(offset, search_from)
        scheme: Scheme
        if source["source_id"] == "amc-factsheet-2025-04":
            scheme = _scheme_at(spans, offset, "general")
        else:
            scheme = source["scheme"]
        chunks.append(
            {
                "id": f"{source['source_id']}-{index}",
                "text": stripped,
                "source_url": source["url"],
                "doc_type": source["doc_type"],
                "title": source["title"],
                "scheme": scheme,
                "source_id": source["source_id"],
                "ingested_at": ingested_at,
                "page": _page_at(text, offset) if source["format"] == "pdf" else None,
            }
        )
        index += 1
    return chunks


def build_chunks(extracts: dict[str, str] | None = None, ingested_at: str | None = None) -> list[Chunk]:
    ingested_at = ingested_at or date.today().isoformat()
    extracts = extracts or read_extracts()
    chunks: list[Chunk] = []
    for source in SOURCES:
        chunks.extend(chunks_for_source(source, extracts[source["source_id"]], ingested_at))
    return chunks


def write_chunks_txt(chunks: list[Chunk], path: Path = CHUNKS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# chunk_size={CHUNK_SIZE} overlap={CHUNK_OVERLAP} min_chunk={MIN_CHUNK}",
        "",
    ]
    for chunk in chunks:
        page = "" if chunk["page"] is None else str(chunk["page"])
        lines.extend(
            [
                f"===== CHUNK id={chunk['id']} =====",
                f"source_url: {chunk['source_url']}",
                f"doc_type: {chunk['doc_type']}",
                f"title: {chunk['title']}",
                f"scheme: {chunk['scheme']}",
                f"source_id: {chunk['source_id']}",
                f"ingested_at: {chunk['ingested_at']}",
                f"page: {page}",
                "----- TEXT -----",
                chunk["text"],
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def count_chunks_in_file(path: Path = CHUNKS_PATH) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("===== CHUNK id="))


if __name__ == "__main__":
    chunks = build_chunks()
    write_chunks_txt(chunks)
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk["source_id"]] = counts.get(chunk["source_id"], 0) + 1
    print(f"wrote {CHUNKS_PATH} ({len(chunks)} chunks)")
    for source_id, n in counts.items():
        print(f"{source_id}\t{n}")
