"""Load → Chunk → Embed → Store (ChromaDB on disk).

Run once. Skip if collection already has vectors unless --force.
Does not call Groq or start the UI.
"""

from __future__ import annotations

import argparse
import logging

import chromadb

from src.chunk import CHUNKS_PATH, Chunk, build_chunks, count_chunks_in_file, write_chunks_txt
from src.embedder import EMBED_MODEL_NAME, NORMALIZE_EMBEDDINGS, embed_texts
from src.load import ROOT, extract_txt_path, load_all, read_extracts

log = logging.getLogger(__name__)

CHROMA_DIR = ROOT / "data" / "chroma"
COLLECTION_NAME = "mf_faq"


def chroma_client(path: Path = CHROMA_DIR) -> chromadb.PersistentClient:
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_collection(client: chromadb.PersistentClient | None = None):
    client = client or chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "embed_model": EMBED_MODEL_NAME},
    )


def _chroma_metadata(chunk: Chunk) -> dict[str, str | int]:
    meta: dict[str, str | int] = {
        "source_url": chunk["source_url"],
        "doc_type": chunk["doc_type"],
        "title": chunk["title"],
        "scheme": chunk["scheme"],
        "source_id": chunk["source_id"],
        "ingested_at": chunk["ingested_at"],
    }
    if chunk["page"] is not None:
        meta["page"] = chunk["page"]
    return meta


def _ensure_extracts() -> dict[str, str]:
    from src.catalog import SOURCES

    missing = [s["source_id"] for s in SOURCES if not extract_txt_path(s).exists()]
    if missing:
        log.info("extracts missing (%s); running load", ", ".join(missing))
        load_all()
    return read_extracts()


def ingest(*, force: bool = False) -> tuple[int, int]:
    """Embed chunks and upsert into Chroma.

    Returns (collection_count, chunks_txt_count).
    """
    client = chroma_client()
    collection = get_collection(client)
    existing = collection.count()
    if existing > 0 and not force:
        txt_count = count_chunks_in_file()
        log.info(
            "collection %s already has %s vectors; skip ingest (pass --force to rebuild). chunks.txt=%s",
            COLLECTION_NAME,
            existing,
            txt_count,
        )
        return existing, txt_count

    if force and existing > 0:
        log.info("--force: deleting collection %s", COLLECTION_NAME)
        client.delete_collection(COLLECTION_NAME)
        collection = get_collection(client)

    extracts = _ensure_extracts()
    chunks = build_chunks(extracts)
    write_chunks_txt(chunks)
    log.info("chunked %s windows -> %s", len(chunks), CHUNKS_PATH)

    texts = [c["text"] for c in chunks]
    log.info(
        "embedding %s chunks with %s (normalize_embeddings=%s)",
        len(texts),
        EMBED_MODEL_NAME,
        NORMALIZE_EMBEDDINGS,
    )
    embeddings = embed_texts(texts)
    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=texts,
        embeddings=embeddings,
        metadatas=[_chroma_metadata(c) for c in chunks],
    )
    stored = collection.count()
    txt_count = count_chunks_in_file()
    log.info("stored %s vectors in %s; chunks.txt=%s", stored, COLLECTION_NAME, txt_count)
    return stored, txt_count


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ingest MF FAQ corpus into ChromaDB")
    parser.add_argument("--force", action="store_true", help="Rebuild collection even if it exists")
    args = parser.parse_args()
    stored, txt_count = ingest(force=args.force)
    print(f"collection_count\t{stored}")
    print(f"chunks_txt_count\t{txt_count}")
    if stored != txt_count:
        raise SystemExit("collection count does not match chunks.txt")


if __name__ == "__main__":
    main()
