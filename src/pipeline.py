"""Gates → retrieve → Groq → app-side citation. No live web fetch at query time."""

from __future__ import annotations

import argparse
import sys
from typing import TypedDict

from src.catalog import get_source
from src.gates import GateResult, apply_gates
from src.generate import GroqConfigError, GroqGenerateError, answer_from_excerpts, generate_answer
from src.retrieve import retrieve

LOW_SCORE = 0.28


class PipelineAnswer(TypedDict):
    kind: str
    body: str
    source_url: str
    last_updated: str | None
    used_groq: bool


def _format(body: str, source_url: str, last_updated: str | None) -> str:
    lines = [body.strip(), "", f"Source: {source_url}"]
    if last_updated:
        lines.append(f"Last updated from sources: {last_updated}")
    return "\n".join(lines)


def _fallback_url(question: str) -> str:
    q = question.lower()
    if "elss" in q or "tax saver" in q:
        return get_source("elss-sid")["url"]
    if "flexi" in q:
        return get_source("flexicap-html")["url"]
    if "statement" in q or "capital gain" in q:
        return get_source("investor-services")["url"]
    return get_source("investor-services")["url"]


def _from_gate(gate: GateResult) -> PipelineAnswer:
    body = gate["message"] or "This assistant can only share official facts."
    url = gate["citation_url"] or _fallback_url(gate["sanitized_question"])
    return {
        "kind": gate["action"],
        "body": body,
        "source_url": url,
        "last_updated": None,
        "used_groq": False,
    }


def answer_question(question: str) -> PipelineAnswer:
    gate = apply_gates(question)
    if gate["action"] in {"refuse_advice", "refuse_returns"}:
        return _from_gate(gate)

    query = gate["sanitized_question"]
    print(f"[pipeline] question received: {query!r}", flush=True)
    hits = retrieve(query)
    print(f"[pipeline] retrieved {len(hits)} hits", flush=True)
    last_updated = max((h["ingested_at"] for h in hits if h["ingested_at"]), default=None)
    citation = hits[0]["source_url"] if hits else _fallback_url(query)

    if not hits or hits[0]["score"] < LOW_SCORE:
        body = (
            "That fact is not in the official pages we indexed. "
            "Please open the linked official page rather than relying on an unsourced answer."
        )
        if gate["action"] == "strip_pii" and gate["message"]:
            body = gate["message"] + " " + body
        return {
            "kind": "low_score",
            "body": body,
            "source_url": citation if hits else _fallback_url(query),
            "last_updated": last_updated,
            "used_groq": False,
        }

    print("[pipeline] calling Groq", flush=True)
    used_groq = True
    try:
        body = generate_answer(query, hits)
        print("[pipeline] Groq response received", flush=True)
    except (GroqConfigError, GroqGenerateError):
        body = answer_from_excerpts(hits)
        used_groq = False
        print("[pipeline] Groq unavailable; using retrieved excerpt", flush=True)
    if gate["action"] == "strip_pii" and gate["message"]:
        body = gate["message"] + " " + body
    return {
        "kind": "answer",
        "body": body,
        "source_url": citation,
        "last_updated": last_updated,
        "used_groq": used_groq,
    }


def render(answer: PipelineAnswer) -> str:
    return _format(answer["body"], answer["source_url"], answer["last_updated"])


def _ask_once(question: str) -> None:
    try:
        print(render(answer_question(question)))
    except (GroqConfigError, GroqGenerateError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)


def _chat_loop() -> None:
    print("Facts-only MF FAQ. Type a question, or 'quit' to exit.")
    print("Advice and return-calculation questions are refused. Groq is used only for factual answers.\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not question:
            continue
        if question.lower() in {"q", "quit", "exit"}:
            return
        print()
        _ask_once(question)
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Facts-only MF FAQ pipeline")
    parser.add_argument("question", nargs="*", help="User question (omit to chat interactively)")
    parser.add_argument("--demo", action="store_true", help="Run factual + advice demos")
    parser.add_argument("--chat", action="store_true", help="Type questions in a loop")
    args = parser.parse_args()

    if args.demo:
        for q in (
            "What is the ELSS lock-in?",
            "Should I buy Flexi Cap?",
        ):
            print(f"Q: {q}")
            _ask_once(q)
            print()
        return

    if args.chat or not args.question:
        _chat_loop()
        return

    _ask_once(" ".join(args.question))


if __name__ == "__main__":
    main()
