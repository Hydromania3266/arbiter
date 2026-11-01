"""News & market intelligence — free sources (Reddit, RSS) + optional X API."""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

DEFAULT_FEEDS: dict[str, str] = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "decrypt": "https://decrypt.co/feed",
    "the_block": "https://www.theblock.co/rss.xml",
}

DEFAULT_SUBREDDITS: list[str] = ["CryptoCurrency", "Bitcoin", "wallstreetbets"]

# keyword aliases used to tag news items to symbols
SYMBOL_ALIASES: dict[str, list[str]] = {
    "BTC/USD": ["bitcoin", "btc", "satoshi"],
    "ETH/USD": ["ethereum", "ether", "eth "],
    "SOL/USD": ["solana", "sol "],
    "AAPL": ["apple", "aapl"],
    "SPY": ["s&p 500", "spy", "stock market"],
}


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: str = ""
    body: str = ""

    @property
    def text(self) -> str:
        extra = f" — {self.body[:200]}" if self.body else ""
        return f"[{self.source}] {self.title}{extra}"


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(s).strip()


def _parse_rss(data: bytes) -> list[NewsItem]:
    from xml.etree import ElementTree

    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return []
    items: list[NewsItem] = []
    # RSS 2.0
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        items.append(NewsItem(
            title=title,
            url=(item.findtext("link") or "").strip(),
            source="rss",
            published=(item.findtext("pubDate") or "").strip(),
            body=_strip_html((item.findtext("description") or "")[:300]),
        ))
    # Atom
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", namespaces=ns) or "").strip()
        if not title:
            continue
        link_el = entry.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        body = (entry.findtext("a:summary", namespaces=ns)
                or entry.findtext("a:content", namespaces=ns) or "")[:300]
        items.append(NewsItem(
            title=title, url=link, source="rss",
            published=(entry.findtext("a:updated", namespaces=ns) or "").strip(),
            body=_strip_html(body),
        ))
    return items


class NewsService:
    """Aggregates market news from free sources with a TTL cache."""

    def __init__(self, poll_minutes: int = 15, x_bearer: str = "", max_items: int = 50):
        self.poll_seconds = poll_minutes * 60
        self.x_bearer = x_bearer
        self.max_items = max_items
        self._cache: list[NewsItem] | None = None
        self._cache_at: float = 0.0

    async def get_news(self) -> list[NewsItem]:
        if self._cache is not None and time.monotonic() - self._cache_at < self.poll_seconds:
            return self._cache
        tasks = [self._fetch_reddit(), self._fetch_rss()]
        if self.x_bearer:
            tasks.append(self._fetch_x())
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[NewsItem] = []
        for res in results:
            if isinstance(res, BaseException):
                logger.warning(f"News source failed: {res}")
                continue
            items.extend(res)
        # de-dup by title
        seen: set[str] = set()
        unique: list[NewsItem] = []
        for it in items:
            key = it.title.lower()[:80]
            if key and key not in seen:
                seen.add(key)
                unique.append(it)
        self._cache = unique[: self.max_items]
        self._cache_at = time.monotonic()
        logger.info(f"News: collected {len(self._cache)} items")
        return self._cache

    # ── sources ────────────────────────────────────────────────────────────

    async def _fetch_reddit(self) -> list[NewsItem]:
        headers = {"User-Agent": "ai-trading-bot/0.1"}
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            tasks = [
                client.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=15")
                for sub in DEFAULT_SUBREDDITS
            ]
            resp = await asyncio.gather(*tasks, return_exceptions=True)
            items: list[NewsItem] = []
            for r in resp:
                if not isinstance(r, httpx.Response) or r.status_code != 200:
                    continue
                try:
                    children = r.json().get("data", {}).get("children", [])
                except ValueError:
                    continue
                for post in children:
                    d = post.get("data", {})
                    if d.get("score", 0) < 20:  # skip low-signal posts
                        continue
                    items.append(NewsItem(
                        title=d.get("title", ""),
                        url="https://www.reddit.com" + d.get("permalink", ""),
                        source=f"r/{d.get('subreddit', '')}",
                        body=_strip_html(d.get("selftext", "")[:300]),
                    ))
            return items

    async def _fetch_rss(self) -> list[NewsItem]:
        async with httpx.AsyncClient(timeout=15) as client:
            tasks = [client.get(url) for url in DEFAULT_FEEDS.values()]
            resp = await asyncio.gather(*tasks, return_exceptions=True)
            items: list[NewsItem] = []
            for name, r in zip(DEFAULT_FEEDS, resp):
                if not isinstance(r, httpx.Response) or r.status_code != 200:
                    continue
                for it in _parse_rss(r.content):
                    it.source = name
                    items.append(it)
            return items

    async def _fetch_x(self) -> list[NewsItem]:
        """X/Twitter via official v2 API — requires a bearer token with read scope.

        The free tier has very low read quotas; Basic tier ($100/mo) is the
        practical minimum. If no token is set this source is skipped.
        """
        items: list[NewsItem] = []
        headers = {"Authorization": f"Bearer {self.x_bearer}"}
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            r = await client.get(
                "https://api.x.com/2/tweets/search/recent",
                params={
                    "query": "bitcoin OR ethereum OR solana OR \"stock market\" min_faves:100 -is:retweet",
                    "max_results": "20",
                    "tweet.fields": "created_at",
                },
            )
            if r.status_code != 200:
                logger.warning(f"X API error {r.status_code}: {r.text[:200]}")
                return items
            for t in r.json().get("data", []):
                items.append(NewsItem(
                    title=t.get("text", "")[:200],
                    url=f"https://x.com/i/status/{t.get('id', '')}",
                    source="X",
                ))
        return items

    # ── helpers ────────────────────────────────────────────────────────────

    def brief(self, items: list[NewsItem], max_items: int = 25) -> str:
        lines = [it.text for it in items[:max_items]]
        return "\n".join(lines) if lines else "(no news available)"

    def tag_symbols(self, items: list[NewsItem]) -> dict[str, list[NewsItem]]:
        """Group news items by the symbols they mention."""
        out: dict[str, list[NewsItem]] = {}
        for it in items:
            text = (it.title + " " + it.body).lower()
            for symbol, aliases in SYMBOL_ALIASES.items():
                if any(a in text for a in aliases):
                    out.setdefault(symbol, []).append(it)
        return out
