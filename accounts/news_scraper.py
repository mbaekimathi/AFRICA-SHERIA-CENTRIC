"""Multi-source news search, article enrichment, deduplication, and ranking."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import (
    parse_qs,
    quote_plus,
    unquote,
    urlencode,
    urljoin,
    urlsplit,
)
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
    urlopen,
)
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from django.core.cache import cache

from .country_codes import COUNTRY_DIAL_CODES


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
FEED_TIMEOUT_SECONDS = 10
ARTICLE_TIMEOUT_SECONDS = 5
MAX_ENRICHED_ARTICLES = 10
USER_AGENT = (
    "Mozilla/5.0 (compatible; SheriaCentricNewsResearch/2.0; "
    "+https://baunilawgroup.com)"
)

COUNTRY_NAMES = {iso: name for iso, name, _dial in COUNTRY_DIAL_CODES}
INDUSTRY_TERMS = {
    "legal": "law legal courts justice",
    "finance": "finance banking investment",
    "technology": "technology digital software",
    "healthcare": "healthcare health medicine",
    "energy": "energy power electricity oil gas renewables",
    "real-estate": "real estate property construction",
    "agriculture": "agriculture farming food",
    "manufacturing": "manufacturing industry factories",
    "telecommunications": "telecommunications mobile internet",
    "transport": "transport logistics aviation shipping",
    "education": "education schools universities",
    "government": "government public policy regulation",
    "entertainment": "media entertainment film music",
    "sports": "sports",
    "other": "",
}
PERIOD_TERMS = {"1d": "when:1d", "7d": "when:7d", "30d": "when:30d"}
PERIOD_MAX_AGE_SECONDS = {
    "1d": 1 * 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}
TRUSTED_SOURCE_HINTS = {
    "reuters": 18,
    "associated press": 18,
    "ap news": 18,
    "bbc": 16,
    "court": 16,
    "judiciary": 16,
    "government": 14,
    "gazette": 14,
    "parliament": 14,
    "central bank": 14,
}
_STOP_WORDS = {
    "a", "about", "and", "are", "for", "from", "in", "is", "it", "news",
    "of", "on", "or", "the", "this", "to", "with",
}
# Light expansions so topic filters match common spellings in headlines.
_TERM_EXPANSIONS = {
    "lawfirm": ("lawfirm", "law firm", "law firms", "firm"),
    "lawfirms": ("lawfirm", "lawfirms", "law firm", "law firms", "firm"),
    "softwares": ("software", "softwares"),
    "software": ("software", "softwares"),
}


class NewsScrapeError(ValueError):
    """A safe, user-facing news retrieval error."""


class NewsSearchCancelled(Exception):
    """Raised when a running search is cancelled by its requester."""


@dataclass(frozen=True)
class NewsArticle:
    title: str
    url: str
    source_name: str
    published_at: str
    published_timestamp: float
    provider: str
    description: str = ""
    passages: tuple[str, ...] = ()
    relevance_score: int = 0
    credibility_score: int = 0
    match_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class NewsSearchResult:
    country_code: str
    country_name: str
    industry: str
    requested_details: str
    period: str
    query: str
    articles: list[NewsArticle]
    retrieved_at: str
    providers: tuple[str, ...]
    enriched_count: int


def _keywords(value: str) -> set[str]:
    words = re.findall(r"[^\W_][\w'-]{2,}", (value or "").lower(), re.UNICODE)
    return {word for word in words if word not in _STOP_WORDS}


def _term_variants(term: str) -> set[str]:
    """Return match variants for one topic keyword (plurals / known spellings)."""
    base = (term or "").lower().strip()
    if not base:
        return set()
    variants = {base}
    if base.endswith("ies") and len(base) > 4:
        variants.add(f"{base[:-3]}y")
    elif base.endswith("es") and len(base) > 4:
        variants.add(base[:-2])
    elif base.endswith("s") and len(base) > 3:
        variants.add(base[:-1])
    variants.update(_TERM_EXPANSIONS.get(base, ()))
    return {item for item in variants if item}


def _term_in_text(term: str, text: str) -> bool:
    return any(variant in text for variant in _term_variants(term))


def _matched_terms(terms: set[str], text: str) -> list[str]:
    return sorted(term for term in terms if _term_in_text(term, text))


def _minimum_topic_hits(topic_count: int) -> int:
    """Require meaningful topic coverage — not a single weak keyword leak."""
    if topic_count <= 0:
        return 0
    if topic_count == 1:
        return 1
    if topic_count == 2:
        return 2
    return max(2, (topic_count + 1) // 2)


def _build_query(
    country_code: str,
    industry: str,
    requested_details: str,
    period: str,
    *,
    exact_phrase: str = "",
    excluded_words: str = "",
    source_domain: str = "",
) -> str:
    country_name = COUNTRY_NAMES.get(country_code.upper())
    if not country_name:
        raise NewsScrapeError("Select a supported country.")
    industry_terms = INDUSTRY_TERMS.get(industry)
    if industry_terms is None:
        raise NewsScrapeError("Select a supported industry.")
    period_term = PERIOD_TERMS.get(period)
    if period_term is None:
        raise NewsScrapeError("Select a supported publication period.")

    def or_group(value: str) -> str:
        terms = re.findall(r"[^\s,;]+", value)
        if not terms:
            return ""
        if len(terms) == 1:
            return terms[0]
        return "(" + " OR ".join(terms) + ")"

    # Topic keywords are ANDed so providers cannot satisfy the query with one
    # loose word (e.g. only "management" or only "law").
    topic_terms = sorted(_keywords(requested_details))
    parts: list[str] = []
    if topic_terms:
        parts.append(" ".join(topic_terms))
    elif requested_details.strip():
        parts.append(requested_details.strip())

    # Industry is a soft preference, not a substitute for the topic.
    industry_group = or_group(industry_terms)
    if industry_group:
        parts.append(industry_group)

    parts.append(f'"{country_name}"')
    if exact_phrase:
        parts.append(f'"{exact_phrase.strip()}"')
    parts.extend(
        f"-{word}"
        for word in re.findall(r"[^\s,;]+", excluded_words)
        if word
    )
    if source_domain:
        parts.append(f"site:{source_domain}")
    parts.append(period_term)
    return " ".join(part for part in parts if part)


def _google_feed_url(country_code: str, language: str, query: str) -> str:
    code = country_code.upper()
    return (
        "https://news.google.com/rss/search"
        f"?q={quote_plus(query)}&hl={language}-{code}&gl={code}"
        f"&ceid={code}:{language}"
    )


def _bing_feed_url(country_code: str, language: str, query: str) -> str:
    return (
        "https://www.bing.com/news/search"
        f"?q={quote_plus(query)}&format=rss&setlang={language}"
        f"&cc={country_code.upper()}"
    )


class _SafeArticleRedirectHandler(HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        if self.redirect_count > 4:
            raise NewsScrapeError("The article redirected too many times.")
        target = urljoin(req.full_url, newurl)
        _validate_public_article_url(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _fetch_bytes(
    url: str, *, timeout: int, accept: str, safe_article: bool = False
) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-GB,en;q=0.8",
        },
    )
    try:
        opener = build_opener(_SafeArticleRedirectHandler()) if safe_article else None
        response_context = (
            opener.open(request, timeout=timeout)
            if opener
            else urlopen(request, timeout=timeout)
        )
        with response_context as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                raise NewsScrapeError("A news response was too large to process.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            final_url = response.geturl()
    except HTTPError as exc:
        raise NewsScrapeError(f"A news source returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise NewsScrapeError("A news source could not be reached.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise NewsScrapeError("A news response was too large to process.")
    return raw, final_url


def _parse_published(value: str) -> tuple[str, float]:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return " ".join((value or "").split()), 0.0
    return parsed.strftime("%d %b %Y, %H:%M"), parsed.timestamp()


def _publisher_url(url: str) -> str:
    parsed = urlsplit(url)
    if "bing.com" in (parsed.hostname or ""):
        candidate = parse_qs(parsed.query).get("url", [""])[0]
        if candidate:
            return unquote(candidate)
    return url


def _clean_title(title: str, source_name: str) -> str:
    value = " ".join((title or "").split())
    suffix = f" - {source_name}"
    return value[: -len(suffix)].rstrip() if source_name and value.endswith(suffix) else value


def _parse_feed(raw: bytes, provider: str, *, limit: int = 30) -> list[NewsArticle]:
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise NewsScrapeError("A news source returned an unreadable response.") from exc

    articles: list[NewsArticle] = []
    for item in root.findall("./channel/item"):
        source_element = item.find("source")
        source_name = (
            " ".join((source_element.text or "").split())
            if source_element is not None
            else ""
        )
        title = _clean_title(item.findtext("title") or "", source_name)
        url = _publisher_url((item.findtext("link") or "").strip())
        if not title or not url:
            continue
        published_at, timestamp = _parse_published(item.findtext("pubDate") or "")
        articles.append(
            NewsArticle(
                title=title,
                url=url,
                source_name=source_name,
                published_at=published_at,
                published_timestamp=timestamp,
                provider=provider,
            )
        )
        if len(articles) >= limit:
            break
    return articles


def _fetch_feed(provider: str, url: str) -> list[NewsArticle]:
    raw, _final_url = _fetch_bytes(
        url,
        timeout=FEED_TIMEOUT_SECONDS,
        accept="application/rss+xml, application/xml, text/xml",
    )
    return _parse_feed(raw, provider)


def _normalize_title(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.lower(), re.UNICODE))


def _deduplicate(articles: list[NewsArticle]) -> list[NewsArticle]:
    unique: list[NewsArticle] = []
    normalized_titles: list[str] = []
    seen_urls: set[str] = set()
    for article in sorted(
        articles, key=lambda item: item.published_timestamp, reverse=True
    ):
        normalized = _normalize_title(article.title)
        clean_url = article.url.split("#", 1)[0]
        if clean_url in seen_urls:
            continue
        if any(
            SequenceMatcher(None, normalized, existing).ratio() >= 0.88
            for existing in normalized_titles
        ):
            continue
        seen_urls.add(clean_url)
        normalized_titles.append(normalized)
        unique.append(article)
    return unique


def _validate_public_article_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise NewsScrapeError("Invalid article URL.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise NewsScrapeError("Private article URL.")
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(
                hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise NewsScrapeError("Article hostname could not be resolved.") from exc
    if not addresses:
        raise NewsScrapeError("Article hostname could not be resolved.")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise NewsScrapeError("Private article URL.")


def _meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        if tag and tag.get("content"):
            return " ".join(tag["content"].split())
    return ""


def _resolve_google_article_url(url: str) -> str:
    """Best-effort resolution of a Google News RSS article to its publisher."""
    parsed = urlsplit(url)
    if "news.google.com" not in (parsed.hostname or ""):
        return url
    token = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if not token:
        return url
    try:
        raw, _final_url = _fetch_bytes(
            url,
            timeout=ARTICLE_TIMEOUT_SECONDS,
            accept="text/html,application/xhtml+xml",
        )
        soup = BeautifulSoup(raw, "html.parser")
        element = soup.select_one("[data-n-a-sg][data-n-a-ts]")
        if not element:
            return url
        signature = element.get("data-n-a-sg", "")
        timestamp = element.get("data-n-a-ts", "")
        request_context = [
            [
                "en-US",
                "US",
                ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"],
                None,
                None,
                1,
                1,
                "US:en",
                None,
                180,
                None,
                None,
                None,
                None,
                None,
                0,
                None,
                None,
                [1608992183, 723341000],
            ],
            "en-US",
            "US",
            1,
            [2, 3, 4, 8],
            1,
            0,
            "655000234",
            0,
            0,
            None,
            0,
        ]
        rpc_argument = json.dumps(
            ["garturlreq", request_context, token, int(timestamp), signature],
            separators=(",", ":"),
        )
        rpc = [["Fbv4je", rpc_argument, None, "generic"]]
        data = urlencode({"f.req": json.dumps([rpc])}).encode("utf-8")
        request = Request(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            },
        )
        with urlopen(request, timeout=ARTICLE_TIMEOUT_SECONDS) as response:
            response_text = response.read(256 * 1024).decode("utf-8", errors="replace")
        chunks = [chunk for chunk in response_text.split("\n\n") if chunk.startswith("[")]
        if not chunks:
            return url
        envelope = json.loads(chunks[0])
        decoded = json.loads(envelope[0][2])
        publisher_url = decoded[1]
        if isinstance(publisher_url, str):
            _validate_public_article_url(publisher_url)
            return publisher_url
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        ValueError,
        TypeError,
        IndexError,
        KeyError,
        json.JSONDecodeError,
        NewsScrapeError,
    ):
        pass
    return url


def _relevant_passages(
    soup: BeautifulSoup, search_terms: set[str], *, limit: int = 7
) -> tuple[str, ...]:
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    selector = (
        "article p, article h2, article h3, main p, main h2, main h3, "
        "[role='main'] p"
    )
    for index, element in enumerate(soup.select(selector)):
        text = " ".join(element.get_text(" ", strip=True).split())
        normalized = text.lower()
        if len(text) < 60 or len(text) > 900 or normalized in seen:
            continue
        seen.add(normalized)
        score = sum(normalized.count(term) for term in search_terms)
        if score:
            candidates.append((score, -index, text))
    candidates.sort(reverse=True)
    return tuple(text for _score, _index, text in candidates[:limit])


def _enrich_article(article: NewsArticle, search_terms: set[str]) -> NewsArticle:
    publisher_url = _resolve_google_article_url(article.url)
    hostname = (urlsplit(publisher_url).hostname or "").lower()
    if "news.google.com" in hostname:
        return article
    try:
        _validate_public_article_url(publisher_url)
        raw, final_url = _fetch_bytes(
            publisher_url,
            timeout=ARTICLE_TIMEOUT_SECONDS,
            accept="text/html,application/xhtml+xml",
            safe_article=True,
        )
        _validate_public_article_url(final_url)
        soup = BeautifulSoup(raw, "html.parser")
        for element in soup(["script", "style", "noscript", "svg", "template"]):
            element.decompose()
        description = _meta_content(
            soup, "description", "og:description", "twitter:description"
        )
        passages = _relevant_passages(soup, search_terms)
        return replace(
            article,
            url=final_url,
            description=description,
            passages=passages,
        )
    except (NewsScrapeError, UnicodeError, ValueError):
        return article


def _score_article(
    article: NewsArticle,
    *,
    topic_terms: set[str],
    industry_terms: set[str],
    exact_phrase: str,
    excluded_terms: set[str],
    period: str = "",
    now_timestamp: float | None = None,
) -> NewsArticle | None:
    searchable = " ".join(
        [article.title, article.source_name, article.description, *article.passages]
    ).lower()
    if excluded_terms and any(
        _term_in_text(term, searchable) for term in excluded_terms
    ):
        return None

    if exact_phrase and exact_phrase.lower() not in searchable:
        return None

    max_age = PERIOD_MAX_AGE_SECONDS.get(period)
    if (
        max_age
        and article.published_timestamp
        and now_timestamp
        and (now_timestamp - article.published_timestamp) > max_age
    ):
        return None

    topic_matched = _matched_terms(topic_terms, searchable)
    required_hits = _minimum_topic_hits(len(topic_terms))
    # Exact phrase is the hard gate when set; otherwise require real topic coverage.
    if not exact_phrase and topic_terms and len(topic_matched) < required_hits:
        return None
    if exact_phrase and topic_terms and not topic_matched and not industry_terms:
        return None

    title_text = article.title.lower()
    title_matches = _matched_terms(set(topic_matched), title_text)
    industry_matched = _matched_terms(industry_terms, searchable)

    relevance = len(topic_matched) * 14 + len(title_matches) * 12
    relevance += min(len(industry_matched), 3) * 3
    reasons: list[str] = []
    if title_matches:
        reasons.append(f"Title matches: {', '.join(title_matches[:4])}")
    elif topic_matched:
        reasons.append(f"Topic matches: {', '.join(topic_matched[:4])}")
    if industry_matched and not topic_terms:
        reasons.append(f"Industry matches: {', '.join(industry_matched[:3])}")
    if exact_phrase:
        relevance += 30
        reasons.append("Contains the exact phrase")
    if article.passages:
        relevance += 12
        reasons.append("Relevant passages extracted")

    source_lower = article.source_name.lower()
    credibility = max(
        (
            score
            for source, score in TRUSTED_SOURCE_HINTS.items()
            if source in source_lower
        ),
        default=5,
    )
    if credibility >= 14:
        reasons.append("Recognised authoritative source")
    return replace(
        article,
        relevance_score=min(relevance, 100),
        credibility_score=credibility,
        match_reasons=tuple(reasons),
    )


def _cache_key(**filters: str) -> str:
    raw = "|".join(f"{key}={filters[key]}" for key in sorted(filters))
    return "latest-news:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def search_latest_news(
    *,
    country_code: str,
    industry: str,
    requested_details: str,
    period: str,
    language: str = "en",
    sort_by: str = "relevance",
    exact_phrase: str = "",
    excluded_words: str = "",
    source_domain: str = "",
    progress_callback=None,
    cancel_callback=None,
) -> NewsSearchResult:
    """Search, enrich, deduplicate, filter, and rank current news."""
    def report(percent: int, label: str) -> None:
        if cancel_callback and cancel_callback():
            raise NewsSearchCancelled()
        if progress_callback:
            progress_callback(percent, label)

    report(3, "Preparing search filters")
    code = country_code.upper()
    query = _build_query(
        code,
        industry,
        requested_details,
        period,
        exact_phrase=exact_phrase,
        excluded_words=excluded_words,
        source_domain=source_domain,
    )
    filters = {
        "country": code,
        "industry": industry,
        "details": requested_details,
        "period": period,
        "language": language,
        "sort": sort_by,
        "phrase": exact_phrase,
        "excluded": excluded_words,
        "source": source_domain,
    }
    key = _cache_key(**filters)
    cached = cache.get(key)
    if cached:
        report(100, "Loaded cached results")
        return cached

    report(8, "Searching news providers")
    feed_urls = {
        "Google News": _google_feed_url(code, language, query),
        "Bing News": _bing_feed_url(code, language, query),
    }
    articles: list[NewsArticle] = []
    successful_providers: list[str] = []
    with ThreadPoolExecutor(max_workers=len(feed_urls)) as executor:
        futures = {
            executor.submit(_fetch_feed, provider, url): provider
            for provider, url in feed_urls.items()
        }
        for future in as_completed(futures):
            provider = futures[future]
            try:
                provider_articles = future.result()
            except NewsScrapeError:
                continue
            if provider_articles:
                successful_providers.append(provider)
                articles.extend(provider_articles)
            report(
                8 + round(17 * len(successful_providers) / len(feed_urls)),
                f"Received results from {provider}",
            )
    if not successful_providers:
        raise NewsScrapeError(
            "Latest news could not be retrieved from the available sources."
        )

    report(28, "Removing duplicate reports")
    unique = _deduplicate(articles)
    topic_terms = _keywords(requested_details)
    industry_terms = _keywords(INDUSTRY_TERMS.get(industry, ""))
    # Enrichment hunts passages using the researcher's topic, not broad industry
    # words that would keep unrelated legal/finance stories.
    search_terms = set(topic_terms) | _keywords(exact_phrase)
    if not search_terms:
        search_terms = set(industry_terms)
    excluded_terms = _keywords(excluded_words.replace(",", " "))
    now_timestamp = datetime.now(timezone.utc).timestamp()

    if topic_terms or exact_phrase:
        # Prefer enriching articles whose titles already look on-topic.
        def _prefilter_rank(article: NewsArticle) -> tuple[int, float]:
            text = f"{article.title} {article.source_name}".lower()
            topic_hits = len(_matched_terms(topic_terms, text))
            phrase_hit = (
                1 if exact_phrase and exact_phrase.lower() in text else 0
            )
            return (phrase_hit + topic_hits, article.published_timestamp)

        unique.sort(key=_prefilter_rank, reverse=True)

    enrichment_targets = unique[:MAX_ENRICHED_ARTICLES]
    enriched_by_url: dict[str, NewsArticle] = {}
    report(34, "Opening top articles")
    with ThreadPoolExecutor(max_workers=MAX_ENRICHED_ARTICLES) as executor:
        futures = {
            executor.submit(_enrich_article, article, search_terms): article.url
            for article in enrichment_targets
        }
        for index, future in enumerate(as_completed(futures), start=1):
            enriched_by_url[futures[future]] = future.result()
            report(
                34 + round(50 * index / max(len(futures), 1)),
                f"Analysed article {index} of {len(futures)}",
            )

    report(88, "Scoring relevance and source quality")
    scored: list[NewsArticle] = []
    for article in unique:
        enriched = enriched_by_url.get(article.url, article)
        scored_article = _score_article(
            enriched,
            topic_terms=topic_terms,
            industry_terms=industry_terms,
            exact_phrase=exact_phrase,
            excluded_terms=excluded_terms,
            period=period,
            now_timestamp=now_timestamp,
        )
        if scored_article is not None:
            scored.append(scored_article)

    if source_domain:
        wanted = source_domain.lower().removeprefix("www.")
        scored = [
            article
            for article in scored
            if wanted in (urlsplit(article.url).hostname or "").lower()
            or wanted in article.source_name.lower()
        ]

    if sort_by == "newest":
        scored.sort(key=lambda item: item.published_timestamp, reverse=True)
    elif sort_by == "credibility":
        scored.sort(
            key=lambda item: (
                item.credibility_score,
                item.relevance_score,
                item.published_timestamp,
            ),
            reverse=True,
        )
    else:
        scored.sort(
            key=lambda item: (
                item.relevance_score,
                item.published_timestamp,
            ),
            reverse=True,
        )

    result = NewsSearchResult(
        country_code=code,
        country_name=COUNTRY_NAMES[code],
        industry=industry,
        requested_details=requested_details,
        period=period,
        query=query,
        articles=scored[:30],
        retrieved_at=datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
        providers=tuple(sorted(successful_providers)),
        enriched_count=sum(
            bool(article.description or article.passages) for article in scored
        ),
    )
    cache.set(key, result, timeout=10 * 60)
    report(100, "Search complete")
    return result
