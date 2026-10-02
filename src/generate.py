"""Groq generation grounded in retrieved chunks. Citation is applied in the pipeline."""

from __future__ import annotations

import os

from groq import Groq

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
from src.retrieve import Hit

DEFAULT_MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = """You are a facts-only mutual fund FAQ assistant for official ICICI Prudential / AMFI pages.
Use ONLY the numbered source excerpts. Do not use outside knowledge.
Prefer excerpt [1] when it answers the question. Ignore numbers that belong to a different scheme than the one named in the question.
Answer in at most 3 short sentences.
Do not give buy/sell/hold advice. Do not compute or compare returns.
Do not invent expense ratios, exit loads, SIP amounts, lock-in periods, NAV, riskometer, or benchmarks.
If the excerpts do not contain the asked fact, say that it is not in the retrieved official excerpts.
Do not include a source URL or a last-updated line; the application adds those."""


class GroqConfigError(RuntimeError):
    pass


class GroqGenerateError(RuntimeError):
    pass


def _load_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path)


def groq_client() -> Groq:
    _load_env()
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise GroqConfigError(
            "GROQ_API_KEY is missing. Copy .env.example to .env and add your Groq key. "
            "This assistant will not answer without it."
        )
    return Groq(api_key=key, timeout=30.0)


def groq_model() -> str:
    _load_env()
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _chunk_block(hits: list[Hit]) -> str:
    parts: list[str] = []
    for i, hit in enumerate(hits, start=1):
        page = f" page={hit['page']}" if hit["page"] is not None else ""
        parts.append(
            f"[{i}] scheme={hit['scheme']} doc={hit['source_id']}{page} url={hit['source_url']}\n{hit['text']}"
        )
    return "\n\n".join(parts)


def generate_answer(question: str, hits: list[Hit]) -> str:
    """Call Groq. Returns the model body only (no citation)."""
    user = (
        f"Question: {question}\n\n"
        f"Official excerpts:\n{_chunk_block(hits)}"
    )
    try:
        client = groq_client()
        # gpt-oss uses reasoning tokens; a small max_tokens can leave message.content empty.
        response = client.chat.completions.create(
            model=groq_model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0,
            max_tokens=1024,
            extra_body={"reasoning_effort": "low"},
        )
    except GroqConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface provider failures to the user
        raise GroqGenerateError(
            "The language model is unavailable right now. No unsourced answer was generated. Please try again later."
        ) from exc

    message = response.choices[0].message if response.choices else None
    body = _message_text(message)
    if not body:
        raise GroqGenerateError(
            "The language model returned an empty answer. No unsourced fallback was used."
        )
    return _trim_sentences(body)


def _message_text(message: object | None) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            else:
                text = getattr(item, "text", None)
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        joined = " ".join(parts).strip()
        if joined:
            return joined
    return ""


def _trim_sentences(text: str) -> str:
    compact = " ".join(text.split())
    sentences: list[str] = []
    buf = ""
    for char in compact:
        buf += char
        if char in ".?!" and buf.strip():
            sentences.append(buf.strip())
            buf = ""
            if len(sentences) == 3:
                break
    if buf.strip() and len(sentences) < 3:
        sentences.append(buf.strip())
    return " ".join(sentences)
