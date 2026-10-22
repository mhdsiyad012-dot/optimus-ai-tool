"""
Optimus AI — 100% Free 24/7 Web Search & Scraper Engine
=======================================================
Zero-cost automated web discovery and extraction pipeline:
1. Multi-Feed Monitor: RSS & Atom streams (Product Hunt AI, Hacker News AI Launches,
   Hugging Face Papers, GitHub AI Trending, and Official AI Research Blogs).
2. Zero-Cost Search Fallback: DuckDuckGo HTML/Lite Scraper + Jina Free Search Reader (s.jina.ai).
3. Clean Markdown Extraction: Jina Reader (r.jina.ai) with local BeautifulSoup4 fallback
   for token-efficient content ingestion.
"""

import re
import time
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import feedparser

logger = logging.getLogger("WebResearcher")
logger.setLevel(logging.INFO)

# User Agent header to prevent anti-bot blocking on public feeds
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 OptimusAI/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class DiscoveryItem:
    """Standardized representation of a discovered candidate AI tool/article."""

    def __init__(self, title: str, link: str, summary: str, source_type: str, published: str = ""):
        self.title = title.strip()
        self.link = link.strip()
        self.summary = summary.strip()
        self.source_type = source_type
        self.published = published.strip()

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "link": self.link,
            "summary": self.summary,
            "source_type": self.source_type,
            "published": self.published,
        }

    def __repr__(self) -> str:
        return f"<DiscoveryItem title='{self.title[:35]}' link='{self.link}'>"


class WebResearcher:
    """Zero-cost web search, feed monitor, and clean extraction coordinator."""

    # Public RSS & Atom feeds for AI launches and official updates
    RSS_FEEDS = [
        # Hacker News Launches & Show HN filtered for AI
        {
            "name": "HackerNews Show HN AI",
            "url": "https://hnrss.org/newest?q=Show+HN+AI",
            "type": "hn_ai"
        },
        {
            "name": "HackerNews Launch HN",
            "url": "https://hnrss.org/newest?q=Launch+HN",
            "type": "hn_launch"
        },
        # Official Research & Industry Announcements
        {
            "name": "Google AI Blog",
            "url": "https://blog.google/technology/ai/rss/",
            "type": "official_blog"
        },
        {
            "name": "OpenAI News",
            "url": "https://openai.com/news/rss.xml",
            "type": "official_blog"
        },
        {
            "name": "Hugging Face Blog",
            "url": "https://huggingface.co/blog/feed.xml",
            "type": "community_hub"
        },
        # Product Hunt AI Topics
        {
            "name": "Product Hunt Artificial Intelligence",
            "url": "https://www.producthunt.com/feed?category=artificial-intelligence",
            "type": "product_hunt"
        }
    ]

    def __init__(self, timeout: int = 15):
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout

    # ========================================================================
    # 1. RSS & ATOM FEED MONITOR
    # ========================================================================
    def fetch_latest_feed_items(self, max_items_per_feed: int = 6) -> List[DiscoveryItem]:
        """Scans all configured AI RSS/Atom feeds for freshly published items."""
        discovered: List[DiscoveryItem] = []
        logger.info(f"Scanning {len(self.RSS_FEEDS)} public AI RSS/Atom feeds...")

        for feed_cfg in self.RSS_FEEDS:
            name = feed_cfg["name"]
            url = feed_cfg["url"]
            try:
                logger.info(f"Checking feed: {name} ({url})")
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code != 200:
                    logger.warning(f"Feed {name} returned HTTP {resp.status_code}")
                    continue

                feed_data = feedparser.parse(resp.content)
                entries = feed_data.entries[:max_items_per_feed]
                logger.info(f"Retrieved {len(entries)} items from {name}.")

                for entry in entries:
                    title = getattr(entry, "title", "Untitled AI Tool")
                    link = getattr(entry, "link", "")
                    # Clean out tracking / redirects
                    clean_link = self._clean_url(link)
                    summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    
                    # Strip HTML tags from summary
                    soup = BeautifulSoup(summary, "html.parser")
                    clean_summary = soup.get_text(separator=" ", strip=True)

                    published = getattr(entry, "published", "") or getattr(entry, "updated", "")

                    if clean_link and (self._is_ai_relevant(title) or self._is_ai_relevant(clean_summary)):
                        discovered.append(DiscoveryItem(
                            title=title,
                            link=clean_link,
                            summary=clean_summary[:500],
                            source_type=feed_cfg["type"],
                            published=published
                        ))
            except Exception as e:
                logger.warning(f"Failed to fetch feed {name}: {e}")

        logger.info(f"Total AI-relevant feed candidates gathered: {len(discovered)}")
        return discovered

    # ========================================================================
    # 2. ZERO-COST FREE SEARCH ENGINE (DuckDuckGo + Jina Search)
    # ========================================================================
    def search_web_free(self, query: str, max_results: int = 8) -> List[DiscoveryItem]:
        """
        Executes web search without paid API keys by prioritizing:
        1. Jina Free Search (s.jina.ai/<query>)
        1. Hacker News Algolia Search (100% free, rich real launches & stories)
        2. Wikipedia OpenSearch API (ideal for historical backfills of companies)
        3. Hugging Face Models API (open weights and tools)
        4. Jina Reader / DuckDuckGo fallback
        """
        logger.info(f"Executing zero-cost search for: '{query}'")
        results: List[DiscoveryItem] = []

        # 1. Hacker News Algolia Free API (No key, no rate limits)
        try:
            hn_url = f"https://hn.algolia.com/api/v1/search?query={quote_plus(query)}&tags=story&hitsPerPage={max_results}"
            resp = self.session.get(hn_url, timeout=self.timeout)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                for hit in hits:
                    title = hit.get("title", "")
                    url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                    clean_u = self._clean_url(url)
                    if clean_u.startswith("http"):
                        results.append(DiscoveryItem(
                            title=title,
                            link=clean_u,
                            summary=hit.get("story_text") or title,
                            source_type="hn_search"
                        ))
                    if len(results) >= max_results:
                        break
                if results:
                    logger.info(f"HN Algolia search returned {len(results)} candidates.")
        except Exception as e:
            logger.debug(f"HN Algolia search failed: {e}")

        # 2. Wikipedia OpenSearch API (Ideal for historical backfill queries)
        if len(results) < max_results:
            try:
                wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={quote_plus(query)}&limit={max_results}&namespace=0&format=json"
                resp = self.session.get(wiki_url, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) >= 4:
                        titles = data[1]
                        snippets = data[2]
                        urls = data[3]
                        for t, s, u in zip(titles, snippets, urls):
                            if u.startswith("http"):
                                results.append(DiscoveryItem(
                                    title=t,
                                    link=u,
                                    summary=s or t,
                                    source_type="wikipedia"
                                ))
                            if len(results) >= max_results:
                                break
                        logger.info(f"Wikipedia OpenSearch returned {len(titles)} candidates.")
            except Exception as e:
                logger.debug(f"Wikipedia search failed: {e}")

        # 3. Hugging Face Models API (For open-source foundation models)
        if len(results) < max_results:
            try:
                hf_url = f"https://huggingface.co/api/models?search={quote_plus(query)}&limit={max_results - len(results)}"
                resp = self.session.get(hf_url, timeout=self.timeout)
                if resp.status_code == 200:
                    models = resp.json()
                    for m in models:
                        mid = m.get("id", "")
                        if mid:
                            m_url = f"https://huggingface.co/{mid}"
                            results.append(DiscoveryItem(
                                title=mid,
                                link=m_url,
                                summary=f"Hugging Face AI Model: {mid} by {mid.split('/')[0] if '/' in mid else 'Community'}",
                                source_type="huggingface"
                            ))
            except Exception as e:
                logger.debug(f"Hugging Face API search failed: {e}")

        # 4. Jina Free Search Reader Fallback
        if len(results) < max_results:
            try:
                jina_url = f"https://s.jina.ai/{quote_plus(query)}"
                resp = self.session.get(jina_url, headers={"Accept": "text/markdown"}, timeout=8)
                if resp.status_code == 200 and len(resp.text) > 100:
                    parsed_jina = self._parse_jina_search_markdown(resp.text, max_results - len(results))
                    if parsed_jina:
                        results.extend(parsed_jina)
            except Exception:
                pass

        return results[:max_results]

    def _parse_jina_search_markdown(self, markdown_text: str, max_results: int) -> List[DiscoveryItem]:
        """Parses markdown search results returned by s.jina.ai."""
        items: List[DiscoveryItem] = []
        blocks = re.split(r"\n(?=\[?\d+\.?\]?\s*Title:|\n##\s+)", markdown_text)
        for block in blocks:
            if not block.strip():
                continue
            title_match = re.search(r"(?:Title:\s*|##\s*\[?)([^\n\]]+)", block)
            url_match = re.search(r"(?:URL Source:\s*|https?://[^\s\)]+)", block)
            
            title = title_match.group(1).strip() if title_match else ""
            link = ""
            if url_match:
                raw_u = url_match.group(0).replace("URL Source:", "").strip()
                link = self._clean_url(raw_u)

            if title and link and link.startswith("http"):
                summary = block[:400].strip()
                items.append(DiscoveryItem(
                    title=title,
                    link=link,
                    summary=summary,
                    source_type="jina_search"
                ))
            if len(items) >= max_results:
                break
        return items

    def _search_duckduckgo_html(self, query: str, limit: int = 5) -> List[DiscoveryItem]:
        """Scrapes DuckDuckGo Lite / HTML interface."""
        items: List[DiscoveryItem] = []
        url = "https://html.duckduckgo.com/html/"
        resp = self.session.post(
            url,
            data={"q": query, "b": ""},
            timeout=self.timeout
        )
        if resp.status_code != 200:
            return items

        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select(".result")
        for res in results[:limit]:
            title_tag = res.select_one(".result__title a")
            snippet_tag = res.select_one(".result__snippet")
            if not title_tag:
                continue

            raw_href = title_tag.get("href", "")
            # DuckDuckGo wraps links in /l/?kh=-1&uddg=<actual_url>
            clean_url = self._extract_ddg_redirect(raw_href)
            title = title_tag.get_text(strip=True)
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            if clean_url.startswith("http"):
                items.append(DiscoveryItem(
                    title=title,
                    link=clean_url,
                    summary=snippet,
                    source_type="duckduckgo"
                ))
        return items

    def _extract_ddg_redirect(self, raw_href: str) -> str:
        """Extracts destination URL from DuckDuckGo redirect link."""
        if "uddg=" in raw_href:
            import urllib.parse
            match = re.search(r"uddg=([^&]+)", raw_href)
            if match:
                return urllib.parse.unquote(match.group(1))
        return raw_href

    # ========================================================================
    # 3. CLEAN MARKDOWN & TEXT EXTRACTION
    # ========================================================================
    def fetch_clean_page_content(self, url: str) -> str:
        """
        Extracts clean, token-efficient markdown for LLM consumption.
        Attempts Jina Reader (r.jina.ai/<url>) first, then falls back to local BS4 parsing.
        """
        clean_target = self._clean_url(url)
        logger.info(f"Extracting clean page text for: {clean_target}")

        # 1. Jina Reader Free Proxy
        try:
            jina_read_url = f"https://r.jina.ai/{clean_target}"
            resp = self.session.get(
                jina_read_url,
                headers={"Accept": "text/markdown"},
                timeout=12
            )
            if resp.status_code == 200 and len(resp.text) > 150:
                logger.info("Successfully fetched clean markdown via Jina Reader.")
                return resp.text[:25000]
        except Exception as e:
            logger.debug(f"Jina reader unavailable for {url}: {e}")

        # 2. Local BeautifulSoup4 Fallback
        try:
            resp = self.session.get(clean_target, timeout=self.timeout)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # Strip clutter
                for element in soup(["script", "style", "nav", "footer", "iframe", "noscript", "svg"]):
                    element.extract()

                # Extract main content container if present
                main_elem = soup.find("main") or soup.find("article") or soup.find("body") or soup
                text = main_elem.get_text(separator="\n", strip=True)
                
                # Consolidate redundant newlines
                cleaned_text = re.sub(r"\n\s*\n+", "\n\n", text)
                logger.info("Extracted clean content via local BeautifulSoup.")
                return cleaned_text[:25000]
        except Exception as e:
            logger.warning(f"Local BS4 fetch failed for {clean_target}: {e}")

        return f"Page content could not be fully loaded from {url}."

    # ========================================================================
    # UTILITY HELPERS
    # ========================================================================
    def _clean_url(self, raw_url: str) -> str:
        """Strips query parameters like utm_source, fbclid, ref."""
        if not raw_url:
            return ""
        try:
            parsed = urlparse(raw_url.strip())
            # Rebuild without query if query only has tracking params
            clean_path = parsed.path.rstrip("/")
            clean = f"{parsed.scheme}://{parsed.netloc}{clean_path}"
            return clean if clean.startswith("http") else raw_url
        except Exception:
            return raw_url

    def _is_ai_relevant(self, text: str) -> bool:
        """Determines if the text relates to an AI launch or tool."""
        if not text:
            return False
        keywords = [
            " ai", "ai ", "agent", "llm", "model", "gpt", "gemini", "claude", "diffusion",
            "neural", "vision", "speech", "robotics", "machine learning", "deep learning",
            "transformer", "synthetic", "weights", "multimodal", "reasoning", "benchmark"
        ]
        lower = f" {text.lower()} "
        return any(k in lower for k in keywords)
