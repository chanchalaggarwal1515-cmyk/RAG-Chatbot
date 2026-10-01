"""Official source catalog for the ICICI Prudential MF FAQ corpus.

Six public AMC/AMFI pages only. No fetching in this module.
"""

from __future__ import annotations

from typing import Literal, TypedDict

DocType = Literal["scheme_page", "factsheet", "sid", "investor_services"]
Scheme = Literal["flexicap", "elss", "largecap", "general"]
SourceFormat = Literal["html", "pdf"]


class Source(TypedDict):
    source_id: str
    url: str
    title: str
    doc_type: DocType
    scheme: Scheme
    format: SourceFormat


SOURCES: list[Source] = [
    {
        "source_id": "flexicap-html",
        "url": "https://www.icicipruamc.com/mutual-fund/equity-funds/icici-prudential-flexicap-fund/1822",
        "title": "ICICI Pru Flexicap Fund scheme page",
        "doc_type": "scheme_page",
        "scheme": "flexicap",
        "format": "html",
    },
    {
        "source_id": "flexicap-factsheet",
        "url": "https://www.icicipruamc.com/blob/knowledgecentre/factsheet-schemes/Schemes/1.%20Equity%20Schemes/ICICI%20Prudential%20Flexi%20Cap%20Fund.pdf",
        "title": "Flexi Cap Fund factsheet (PDF)",
        "doc_type": "factsheet",
        "scheme": "flexicap",
        "format": "pdf",
    },
    {
        "source_id": "elss-factsheet",
        "url": "https://www.icicipruamc.com/blob/knowledgecentre/factsheet-schemes/Schemes/1.%20Equity%20Schemes/ICICI%20Prudential%20ELSS%20-%20Tax%20Saver%20Fund.pdf",
        "title": "ELSS Tax Saver Fund factsheet (PDF)",
        "doc_type": "factsheet",
        "scheme": "elss",
        "format": "pdf",
    },
    {
        "source_id": "elss-sid",
        "url": "https://portal.amfiindia.com/spages/131.pdf",
        "title": "ELSS Tax Saver Fund SID (AMFI)",
        "doc_type": "sid",
        "scheme": "elss",
        "format": "pdf",
    },
    {
        "source_id": "amc-factsheet-2025-04",
        "url": "https://www.icicipruamc.com/blob/downloads/Files/Historic%20Factsheets/2025-2026/Complete%20Factsheet%20April%202025.pdf",
        "title": "Complete AMC factsheet, April 2025 (includes Large Cap / Bluechip)",
        "doc_type": "factsheet",
        "scheme": "general",
        "format": "pdf",
    },
    {
        "source_id": "investor-services",
        "url": "https://www.icicipruamc.com/investor-services",
        "title": "Investor Services (account, capital gains, STT statements)",
        "doc_type": "investor_services",
        "scheme": "general",
        "format": "html",
    },
]


def get_source(source_id: str) -> Source:
    for source in SOURCES:
        if source["source_id"] == source_id:
            return source
    raise KeyError(f"Unknown source_id: {source_id}")


if __name__ == "__main__":
    assert len(SOURCES) == 6
    for source in SOURCES:
        print(f"{source['source_id']}\t{source['url']}")
