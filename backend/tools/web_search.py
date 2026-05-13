"""
BKAi Web Search Tool.

Fallback search tool that scrapes hcmut.edu.vn when the local
knowledge base doesn't contain sufficient information.
Domain-restricted to prevent information leakage.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup

from config.settings import get_settings
from tools.vector_search import SearchResult
from utils.logger import get_logger
from utils.text_cleaning import normalize_unicode

logger = get_logger(__name__)

# Google search restricted to hcmut.edu.vn
SEARCH_URL = "https://www.google.com/search"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def web_search(
    query: str,
    max_results: int | None = None,
) -> list[SearchResult]:
    """
    Search the web for HCMUT-specific information.

    Uses Google search restricted to hcmut.edu.vn domain,
    then scrapes the top results for content.

    Args:
        query: Search query.
        max_results: Maximum number of results to return.

    Returns:
        List of SearchResult objects from web pages.
    """
    settings = get_settings()
    domain = settings.web_search.domain
    k = max_results or settings.web_search.max_results
    timeout = settings.web_search.timeout

    # Restrict search to hcmut.edu.vn
    search_query = f"site:{domain} {query}"

    results: list[SearchResult] = []

    try:
        # Fetch Google search results
        urls = await _google_search(search_query, num_results=k, timeout=timeout)

        # Scrape each URL
        for url in urls[:k]:
            if domain not in url:
                continue  # Extra safety: skip non-HCMUT URLs

            content = await _scrape_page(url, timeout=timeout)
            if content and len(content) > 50:
                results.append(SearchResult(
                    content=content[:2000],  # Cap content length
                    metadata={
                        "source_url": url,
                        "source_type": "web",
                        "category": "web_search",
                    },
                    score=0.5,  # Default score for web results
                    source="web",
                ))

    except Exception as e:
        logger.error("web_search_error", error=str(e), query=query[:80])

    logger.info(
        "web_search_complete",
        query=query[:80],
        results=len(results),
    )
    return results


async def _google_search(
    query: str,
    num_results: int = 5,
    timeout: int = 15,
) -> list[str]:
    """Extract URLs from Google search results page."""
    params = {
        "q": query,
        "num": num_results,
        "hl": "vi",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            SEARCH_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    urls: list[str] = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        # Google wraps URLs in /url?q=...
        if href.startswith("/url?q="):
            url = href.split("/url?q=")[1].split("&")[0]
            if "hcmut.edu.vn" in url:
                urls.append(url)

    return urls[:num_results]


async def _scrape_page(url: str, timeout: int = 15) -> str:
    """Scrape and extract main text content from a web page."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            )
            response.raise_for_status()
    except Exception as e:
        logger.warning("scrape_failed", url=url, error=str(e))
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove script and style elements
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Extract text from main content area
    main = soup.find("main") or soup.find("article") or soup.find("body")
    if not main:
        return ""

    text = main.get_text(separator="\n", strip=True)
    text = normalize_unicode(text)

    # Clean up excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()
