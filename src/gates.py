"""Rule-based PII, advice, and returns gates. No LLM, no disk logs of raw user text."""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from src.catalog import get_source

Action = Literal["refuse_advice", "refuse_returns", "strip_pii", "allow"]


class GateResult(TypedDict):
    action: Action
    message: str | None
    citation_url: str | None
    sanitized_question: str
    pii_found: bool


PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.I)
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b")
OTP_RE = re.compile(r"\b(?:otp|one[\s-]?time(?:\s+password)?)\b[:\s-]*\d{4,8}\b", re.I)
OTP_BARE_RE = re.compile(r"\b\d{6}\b")
ACCOUNT_RE = re.compile(
    r"\b(?:folio|account|a\s*/\s*c|bank\s*account|ifsc)[\s:#-]*[A-Z0-9/-]{6,}\b",
    re.I,
)

ADVICE_RE = re.compile(
    r"("
    r"should\s+i\s+(buy|sell|invest|hold|redeem|switch)"
    r"|buy\s+or\s+sell"
    r"|(?:buy|sell|hold|redeem)\s+(?:flexi|elss|the\s+fund|this\s+fund)"
    r"|which\s+(?:fund|scheme|one)\s+is\s+better"
    r"|which\s+(?:is\s+)?(?:better|best)\s+(?:fund|scheme)"
    r"|recommend(?:ed|ation)?"
    r"|portfolio\s+construct"
    r"|is\s+it\s+(?:a\s+)?good\s+(?:time|fund|investment|idea)"
    r"|suitable\s+for\s+me"
    r"|suitability"
    r")",
    re.I,
)

RETURNS_RE = re.compile(
    r"("
    r"\d+\s*(?:year|yr|y)\s*(?:return|cagr|performance)"
    r"|(?:return|cagr|performance)\s+(?:over|for|in)?\s*\d+\s*(?:year|yr|y)"
    r"|trailing\s+returns?"
    r"|compare\s+(?:the\s+)?(?:returns?|cagr|performance)"
    r"|(?:best|top)\s+perform"
    r"|what\s+(?:was|were|is|are)\s+(?:the\s+)?(?:\d+\s*(?:year|yr|y)\s+)?(?:return|cagr)"
    r"|compute\s+(?:returns?|cagr|performance)"
    r"|scheme\s+cagr"
    r")",
    re.I,
)

PII_PATTERNS = (PAN_RE, AADHAAR_RE, EMAIL_RE, PHONE_RE, OTP_RE, ACCOUNT_RE)

SCHEME_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ("flexicap", re.compile(r"flexi\s*cap|flexicap", re.I)),
    ("elss", re.compile(r"\belss\b|tax\s*saver", re.I)),
    ("largecap", re.compile(r"blue\s*chip|bluechip|\blarge\s*cap\b", re.I)),
]


def _scheme_hint(text: str) -> str | None:
    for scheme, pattern in SCHEME_HINTS:
        if pattern.search(text):
            return scheme
    return None


def _advice_url(text: str) -> str:
    scheme = _scheme_hint(text)
    if scheme == "flexicap":
        return get_source("flexicap-html")["url"]
    if scheme == "elss":
        return get_source("elss-factsheet")["url"]
    if scheme == "largecap":
        return get_source("amc-factsheet-2025-04")["url"]
    return get_source("investor-services")["url"]


def _factsheet_url(text: str) -> str:
    scheme = _scheme_hint(text)
    if scheme == "elss":
        return get_source("elss-factsheet")["url"]
    if scheme == "largecap":
        return get_source("amc-factsheet-2025-04")["url"]
    return get_source("flexicap-factsheet")["url"]


def sanitize_pii(text: str) -> tuple[str, bool]:
    """Replace PII with placeholders. Never log the original string."""
    found = False
    cleaned = text
    for pattern in PII_PATTERNS:
        if pattern.search(cleaned):
            found = True
            cleaned = pattern.sub("[REDACTED]", cleaned)
    if OTP_BARE_RE.search(cleaned) and re.search(r"\botp\b", text, re.I):
        found = True
        cleaned = OTP_BARE_RE.sub("[REDACTED]", cleaned)
    return cleaned, found


def apply_gates(question: str) -> GateResult:
    sanitized, pii_found = sanitize_pii(question)

    if ADVICE_RE.search(sanitized):
        url = _advice_url(sanitized)
        return {
            "action": "refuse_advice",
            "message": (
                "This assistant shares official scheme facts only and cannot say whether you should buy, sell, or hold. "
                "Please use the linked official page for product information, and consult a registered adviser for suitability."
            ),
            "citation_url": url,
            "sanitized_question": sanitized,
            "pii_found": pii_found,
        }

    if RETURNS_RE.search(sanitized):
        url = _factsheet_url(sanitized)
        return {
            "action": "refuse_returns",
            "message": (
                "This assistant does not compute, compare, or rank scheme returns. "
                "Please read performance figures only from the official factsheet."
            ),
            "citation_url": url,
            "sanitized_question": sanitized,
            "pii_found": pii_found,
        }

    if pii_found:
        return {
            "action": "strip_pii",
            "message": (
                "Personal identifiers (PAN, Aadhaar, account numbers, OTPs, email, or phone) are not needed and are not stored. "
                "Ask with scheme facts only, such as expense ratio, exit load, lock-in, or how to download a statement."
            ),
            "citation_url": get_source("investor-services")["url"],
            "sanitized_question": sanitized,
            "pii_found": True,
        }

    return {
        "action": "allow",
        "message": None,
        "citation_url": None,
        "sanitized_question": sanitized,
        "pii_found": False,
    }


DEMO_INPUTS = [
    "Should I buy Flexi Cap?",
    "Which fund is better?",
    "What was 5y return?",
    "My PAN is ABCDE1234F, what is the exit load?",
    "What is the exit load of ICICI Prudential Flexi Cap Fund?",
]


if __name__ == "__main__":
    for sample in DEMO_INPUTS:
        result = apply_gates(sample)
        shown = result["sanitized_question"]
        print(f"IN (sanitized): {shown}")
        print(f"  action={result['action']} pii_found={result['pii_found']}")
        if result["message"]:
            print(f"  message={result['message']}")
        if result["citation_url"]:
            print(f"  citation={result['citation_url']}")
        print()

    assert apply_gates("Should I buy Flexi Cap?")["action"] == "refuse_advice"
    assert apply_gates("Which fund is better?")["action"] == "refuse_advice"
    assert apply_gates("What was 5y return?")["action"] == "refuse_returns"
    pan = apply_gates("My PAN is ABCDE1234F, what is the exit load?")
    assert pan["action"] == "strip_pii"
    assert "ABCDE1234F" not in pan["sanitized_question"]
    assert apply_gates("What is the exit load of ICICI Prudential Flexi Cap Fund?")["action"] == "allow"
    print("demo assertions passed")
