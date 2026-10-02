"""Lightweight runtime access to the prebuilt Chroma knowledge store.

This module intentionally has no ingestion, embedding, scraping, or ML imports.
The deployed Streamlit app only needs read access to the already-built store.
"""
from __future__ import annotations

from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = ROOT / "data" / "chroma"
COLLECTION_NAME = "mf_faq"


def chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection():
    return chroma_client().get_collection(name=COLLECTION_NAME)
