"""
BkAI MCP Scraper — fetch admission info from allowed HCMUT domains.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from agents.state import AgentState, format_context, serialize_results
from config.settings import get_settings
from tools.vector_search import SearchResult
from utils.logger import get_logger
from utils.text_cleaning import normalize_unicode

logger = get_logger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SEARCH_PATHS = [
    "https://www.hcmut.edu.vn/vi/news/search?q={query}",
    "https://hcmut.edu.vn/vi/news/search?q={query}",
]


async def scrape_hcmut(query: str, max_pages: int | None = None) -> list[SearchResult]:
    settings = get_settings()
    if not settings.mcp.scraper_enabled:
        return []

    allowed = settings.mcp.allowed_domain_list
    k = max_pages or settings.mcp.max_pages
    timeout = settings.mcp.timeout
    results: list[SearchResult] = []

    urls = await _discover_urls(query, allowed, k, timeout)
    for url in urls[:k]:
        if not _is_allowed(url, allowed):
            continue
        content = await _scrape_page(url, timeout)
        if content and len(content) > 80:
            results.append(SearchResult(
                content=content[:2500],
                metadata={
                    "source_url": url,
                    "source_file": url,
                    "source_type": "mcp_scraper",
                    "category": "web_search",
                },
                score=0.4,
                source="mcp",
            ))

    logger.info("mcp_scrape_complete", query=query[:80], results=len(results))
    return results


async def mcp_scrape_node(state: AgentState) -> dict:
    query = state["original_query"]
    web_results = await scrape_hcmut(query)

    if not web_results:
        return {
            "retrieval_context": state.get("retrieval_context", "") or "Không tìm thấy dữ liệu trên hcmut.edu.vn.",
            "current_step": "mcp_scrape",
        }

    serialized = serialize_results(web_results)
    context = format_context(serialized, max_chars=3000)
    existing = state.get("retrieval_context", "")
    merged = f"{existing}\n\n---\n\n[Dữ liệu từ hcmut.edu.vn]\n{context}" if existing else context

    return {
        "reranked_results": serialized,
        "retrieval_context": merged[:4000],
        "retrieval_decision": "SUFFICIENT",
        "current_step": "mcp_scrape",
    }


def _is_allowed(url: str, allowed_domains: list[str]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(domain in host for domain in allowed_domains)


async def _discover_urls(
    query: str,
    allowed_domains: list[str],
    max_urls: int,
    timeout: int,
) -> list[str]:
    encoded = quote_plus(query)
    found: list[str] = []

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for template in SEARCH_PATHS:
            if len(found) >= max_urls:
                break
            try:
                resp = await client.get(
                    template.format(query=encoded),
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = urljoin(resp.url, a["href"])
                    if _is_allowed(href, allowed_domains) and href not in found:
                        found.append(href)
                    if len(found) >= max_urls:
                        break
            except Exception as e:
                logger.warning("mcp_discover_failed", error=str(e))

        if not found:
            for domain in allowed_domains[:1]:
                seed = f"https://{domain}/vi/news"
                try:
                    resp = await client.get(seed, headers={"User-Agent": USER_AGENT})
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a", href=True)[:20]:
                        href = urljoin(resp.url, a["href"])
                        if _is_allowed(href, allowed_domains) and href not in found:
                            found.append(href)
                except Exception:
                    pass

    return found[:max_urls]


async def _scrape_page(url: str, timeout: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
    except Exception as e:
        logger.warning("mcp_scrape_page_failed", url=url, error=str(e))
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find("body")
    if not main:
        return ""

    text = main.get_text(separator="\n", strip=True)
    text = normalize_unicode(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
