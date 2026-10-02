"""Tiny facts-only FAQ UI. Does not ingest on startup or persist chats to disk."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.gates import sanitize_pii

CHROMA_DIR = ROOT / "data" / "chroma"

EXAMPLES = [
    "What is the expense ratio of ICICI Prudential Flexi Cap Fund?",
    "What is the ELSS lock-in period?",
    "How to download a capital-gains statement?",
]

DISCLAIMER = "Facts-only. No investment advice."
WELCOME = (
    "This is a facts-only ICICI Prudential MF FAQ assistant. "
    "It answers from indexed official AMC/AMFI pages only."
)
REFUSE_KINDS = {"refuse_advice", "refuse_returns"}


def chroma_ready() -> bool:
    """True when the on-disk store exists. Does not open Chroma or ingest."""
    return (CHROMA_DIR / "chroma.sqlite3").exists()


def _render_assistant(item: dict[str, Any]) -> None:
    st.write(item["body"])
    url = item.get("source_url") or ""
    if url:
        st.markdown(f"**Source:** [{url}]({url})")
    if item.get("kind") in REFUSE_KINDS:
        st.caption("No buy, sell, hold, or suitability recommendation.")
    elif item.get("last_updated"):
        st.caption(f"Last updated from sources: {item['last_updated']}")


st.set_page_config(page_title="ICICI Prudential MF FAQ", page_icon="📘", layout="centered")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending" not in st.session_state:
    st.session_state.pending = None

store_ok = chroma_ready()

st.title("ICICI Prudential MF FAQ assistant")
st.write(WELCOME)
st.info(DISCLAIMER)

with st.sidebar:
    st.markdown(f"**{DISCLAIMER}**")
    st.caption("Official public pages only. One source link per answer. Chats are not saved to disk.")

if not store_ok:
    st.error(
        "The knowledge store is missing on this host. "
        "The GitHub repo must include data/chroma (already committed) and the app must be rebuilt. "
        "GROQ_API_KEY must be set in host secrets; local .env is not deployed."
    )

st.write("Try an example:")
for example in EXAMPLES:
    if st.button(example, use_container_width=True, disabled=not store_ok):
        st.session_state.pending = example
        st.rerun()

if not store_ok:
    st.stop()

for item in st.session_state.messages:
    with st.chat_message(item["role"]):
        if item["role"] == "assistant":
            _render_assistant(item)
        else:
            st.write(item["content"])

prompt = st.chat_input("Ask a facts-only question")
if st.session_state.pending:
    prompt = st.session_state.pending
    st.session_state.pending = None

if not prompt:
    st.stop()

shown, _pii_found = sanitize_pii(prompt)
st.session_state.messages.append({"role": "user", "content": shown})
with st.chat_message("user"):
    st.write(shown)

with st.chat_message("assistant"):
    try:
        from src.generate import GroqConfigError, GroqGenerateError
        from src.pipeline import answer_question

        with st.spinner("Looking up official pages…"):
            answer = answer_question(prompt)
        item = {
            "role": "assistant",
            "kind": answer["kind"],
            "body": answer["body"],
            "source_url": answer["source_url"],
            "last_updated": answer["last_updated"],
        }
        _render_assistant(item)
        st.session_state.messages.append(item)
    except (GroqConfigError, GroqGenerateError, RuntimeError) as exc:
        text = str(exc)
        st.error(text)
        st.exception(exc)
        st.session_state.messages.append(
            {
                "role": "assistant",
                "kind": "error",
                "body": text,
                "source_url": "",
                "last_updated": None,
            }
        )
