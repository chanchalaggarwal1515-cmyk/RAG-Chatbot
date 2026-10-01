"""Download official sources and extract inspectable text.

Caches raw HTML/PDF under data/raw/. Reuses cache if the file already exists
and is usable. HTML AMC pages are a JavaScript app, so those are rendered
with Playwright. Does not chunk, embed, or write to a vector store.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.catalog import SOURCES, Source

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT_S = 90
SPA_WAIT_MS = 4000

# Bare /investor-services returns 404 for HTTP clients; official child pages
# still live under that path. Catalog citation URL is unchanged.
HTML_FETCH_URLS: dict[str, list[str]] = {
    "flexicap-html": [
        "https://www.icicipruamc.com/mutual-fund/equity-funds/icici-prudential-flexicap-fund/1822",
    ],
    "investor-services": [
        "https://www.icicipruamc.com/investor-services?type=STATEMENTS",
        "https://www.icicipruamc.com/investor-services/capital-gain",
        "https://www.icicipruamc.com/investor-services/account-statement",
        "https://www.icicipruamc.com/investor-services/pre-login-capital-gain",
    ],
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def raw_bytes_path(source: Source) -> Path:
    return RAW_DIR / f"{source['source_id']}.{source['format']}"


def extract_txt_path(source: Source) -> Path:
    return RAW_DIR / f"{source['source_id']}.txt"


def read_extracts() -> dict[str, str]:
    """Read cached .txt extracts. Raises if any catalog source is missing."""
    extracts: dict[str, str] = {}
    missing: list[str] = []
    for source in SOURCES:
        path = extract_txt_path(source)
        if not path.exists() or path.stat().st_size == 0:
            missing.append(source["source_id"])
            continue
        extracts[source["source_id"]] = path.read_text(encoding="utf-8")
    if missing:
        raise FileNotFoundError(
            "Missing extracts for: " + ", ".join(missing) + ". Run: python -m src.load"
        )
    return extracts


def is_js_shell(html: str) -> bool:
    lowered = html.lower()
    return (
        'id="root"' in lowered
        and "enable javascript" in lowered
        and "<div id=\"root\"></div>" in html.replace(" ", "")
    ) or (
        'id="root"' in lowered and len(BeautifulSoup(html, "html.parser").get_text(strip=True)) < 80
    )


def html_to_text(html_bytes: bytes) -> str:
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    for tag in soup.find_all(["nav", "footer", "header"]):
        tag.decompose()
    return normalize_whitespace(soup.get_text(separator="\n"))


def pdf_to_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    empty_pages = 0
    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = normalize_whitespace(page_text)
        if not page_text:
            empty_pages += 1
            log.warning("empty PDF page (skipped, no OCR): %s page %s", pdf_path.name, index)
            continue
        parts.append(f"[Page {index}]\n{page_text}")
    if empty_pages:
        log.warning("%s: %s empty page(s) skipped", pdf_path.name, empty_pages)
    return "\n\n".join(parts)


def download_pdf_if_needed(source: Source) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = raw_bytes_path(source)
    if dest.exists() and dest.stat().st_size > 0:
        log.info("cache hit %s (%s bytes)", dest.name, dest.stat().st_size)
        return dest

    log.info("fetching %s", source["url"])
    response = requests.get(
        source["url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"},
        timeout=TIMEOUT_S,
        allow_redirects=True,
    )
    response.raise_for_status()
    dest.write_bytes(response.content)
    log.info("saved %s (%s bytes)", dest.name, dest.stat().st_size)
    return dest


def _render_urls_with_playwright(urls: list[str]) -> tuple[str, str]:
    from playwright.sync_api import sync_playwright

    html_parts: list[str] = []
    text_parts: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale="en-IN")
        page = context.new_page()
        for url in urls:
            log.info("rendering HTML %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_S * 1000)
            page.wait_for_timeout(SPA_WAIT_MS)
            html_parts.append(f"<!-- fetched_url: {page.url} -->\n{page.content()}")
            body_text = page.evaluate(
                """() => {
                    const root = document.querySelector('#root') || document.body;
                    return root ? (root.innerText || root.textContent || '') : '';
                }"""
            )
            text_parts.append(f"[URL {url}]\n{normalize_whitespace(body_text or '')}")
        browser.close()
    return "\n\n".join(html_parts), "\n\n".join(text_parts)


def load_html_source(source: Source) -> str:
    """Render JS scheme/service pages; cache rendered HTML + return visible text."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = raw_bytes_path(source)
    txt_path = extract_txt_path(source)
    urls = HTML_FETCH_URLS.get(source["source_id"], [source["url"]])

    cached_usable = False
    if dest.exists() and dest.stat().st_size > 0 and txt_path.exists():
        cached_text = txt_path.read_text(encoding="utf-8")
        cached_html = dest.read_text(encoding="utf-8", errors="ignore")
        if len(cached_text) >= 80 and not is_js_shell(cached_html):
            log.info("cache hit %s (%s bytes)", dest.name, dest.stat().st_size)
            cached_usable = True
            return cached_text

    if dest.exists() and not cached_usable:
        log.info("cached HTML for %s is a JS shell or empty extract; re-rendering", source["source_id"])

    html, text = _render_urls_with_playwright(urls)
    dest.write_text(html, encoding="utf-8")
    log.info("saved rendered %s (%s bytes)", dest.name, dest.stat().st_size)
    return normalize_whitespace(text)


def extract_text(source: Source, raw_path: Path) -> str:
    if source["format"] == "html":
        return html_to_text(raw_path.read_bytes())
    if source["format"] == "pdf":
        return pdf_to_text(raw_path)
    raise ValueError(f"Unsupported format: {source['format']}")


def load_all() -> dict[str, int]:
    """Download/cache all catalog sources and write .txt extracts.

    Returns character counts keyed by source_id.
    """
    counts: dict[str, int] = {}
    for source in SOURCES:
        if source["format"] == "html":
            text = load_html_source(source)
        else:
            raw_path = download_pdf_if_needed(source)
            text = extract_text(source, raw_path)
        txt_path = extract_txt_path(source)
        txt_path.write_text(text, encoding="utf-8")
        counts[source["source_id"]] = len(text)
        log.info("extract %s -> %s chars", source["source_id"], len(text))
        if not text:
            log.warning("extract is empty for %s — fix the loader before chunking", source["source_id"])
    return counts


if __name__ == "__main__":
    print("source_id\tchars")
    for source_id, chars in load_all().items():
        print(f"{source_id}\t{chars}")
