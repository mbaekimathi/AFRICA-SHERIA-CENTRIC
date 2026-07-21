"""Build an editable, attributed blog draft from a selected news result."""

from __future__ import annotations

import re

from django.utils.text import slugify


_STOP_WORDS = {
    "a", "an", "and", "are", "for", "from", "in", "into", "is", "of",
    "on", "or", "the", "to", "with",
}

_INDUSTRY_LABELS = {
    "legal": "law and justice",
    "finance": "finance and banking",
    "technology": "technology",
    "healthcare": "healthcare",
    "energy": "energy",
    "real-estate": "real estate",
    "agriculture": "agriculture",
    "manufacturing": "manufacturing",
    "telecommunications": "telecommunications",
    "transport": "transport and logistics",
    "education": "education",
    "government": "government and public policy",
    "entertainment": "media and entertainment",
    "sports": "sports",
    "other": "the relevant sector",
}


def _truncate_words(value: str, limit: int) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    shortened = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return f"{shortened}…"


def _sentence(value: str) -> str:
    text = " ".join((value or "").split()).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _focus_keyword(filters: dict, original_title: str) -> str:
    exact = " ".join((filters.get("exact_phrase") or "").split())
    requested = " ".join((filters.get("requested_details") or "").split())
    candidate = exact or requested
    words = [
        word
        for word in re.findall(r"[\w'-]+", candidate, flags=re.UNICODE)
        if word.lower() not in _STOP_WORDS
    ][:5]
    if not words:
        words = re.findall(r"[\w'-]+", original_title, flags=re.UNICODE)[:5]
    return _truncate_words(" ".join(words), 70)


def _extract_reported_facts(article: dict) -> list[str]:
    """Extract distinct, attributable sentences without inventing facts."""
    facts: list[str] = []
    seen: set[str] = set()
    values = [article.get("description") or "", *(article.get("passages") or [])]
    for value in values:
        for part in re.split(r"(?<=[.!?])\s+|[\r\n]+", value):
            fact = _sentence(_truncate_words(part, 320))
            key = re.sub(r"\W+", " ", fact).strip().lower()
            if len(key) < 35 or key in seen:
                continue
            seen.add(key)
            facts.append(fact)
            if len(facts) >= 7:
                return facts
    return facts


def _seo_title(title: str, country_name: str) -> str:
    if len(title) >= 50:
        return _truncate_words(title, 60)
    suffix = f" | {country_name} News Analysis"
    return _truncate_words(f"{title}{suffix}", 60)


def build_news_blog_draft(
    *,
    article: dict,
    filters: dict,
    country_name: str,
) -> tuple[dict, dict]:
    """Return EmployeeBlogForm initial values and source context."""
    source_name = article.get("source_name") or "the original publisher"
    source_url = article.get("url") or ""
    published_at = article.get("published_at") or ""
    original_title = _truncate_words(article.get("title") or "News analysis", 180)
    requested_details = " ".join((filters.get("requested_details") or "").split())
    focus_keyword = _focus_keyword(filters, original_title)
    if focus_keyword.lower() in original_title.lower():
        title = _truncate_words(original_title, 60)
    else:
        title = _truncate_words(
            f"{focus_keyword.title()}: {original_title}",
            60,
        )
    if len(title) < 30:
        title = _truncate_words(f"{title}: Key Developments Explained", 60)

    description = _sentence(article.get("description") or "")
    facts = _extract_reported_facts(article)
    if description:
        reported_summary = description
    else:
        reported_summary = (
            f"{source_name} reported on “{original_title}”. The development "
            f"forms part of the latest coverage relevant to {requested_details or 'the selected topic'}."
        )

    key_points = "\n".join(
        f"- {point}" for point in facts
    ) or (
        "- Review the original report for the publisher’s complete account.\n"
        "- Confirm material facts against official records or primary sources.\n"
        "- Distinguish reported statements from findings made by a court or regulator."
    )
    publication_detail = (
        f", published {published_at}" if published_at else ""
    )
    industry = _INDUSTRY_LABELS.get(
        filters.get("industry"), filters.get("industry") or "the relevant sector"
    )
    factual_detail = (
        f"The available source material yielded {len(facts)} specific reported "
        "point" + ("" if len(facts) == 1 else "s") + " for review."
        if facts
        else "The available result contains limited extracted detail, so the original report must be reviewed closely."
    )

    body = f"""## The development at a glance

{source_name}{publication_detail}, reported “{original_title}”. The report concerns {focus_keyword} and may be relevant to organisations, practitioners, policymakers and affected stakeholders in {country_name}.

{reported_summary}

{factual_detail} The analysis below separates those reported facts from editorial context and practical questions.

## What the source reports

{key_points}

These points are attributed to {source_name}; they should be checked against the complete report and any available primary documents before publication.

## Context in {country_name}

This development sits within the wider {industry} landscape. Its importance will depend on the status of the underlying event, the institutions and people involved, and whether the report concerns a final decision, an ongoing process, a proposal or an allegation. Those distinctions can materially change the conclusions readers should draw.

For readers following {focus_keyword}, the immediate value of the report is that it identifies an issue requiring closer attention. The next step is to compare the coverage with official records, legislation, judgments, regulatory notices, company announcements or direct statements where those materials exist.

## Analysis and likely implications

The report may have consequences beyond the headline. In {industry}, new decisions and public developments can affect compliance expectations, contracts, institutional practice, risk assessment and future disputes. The practical impact cannot be determined from a headline alone; it requires a careful reading of the underlying facts and the governing legal or regulatory framework.

Stakeholders should identify who is directly affected, what has formally changed, when the change takes effect and whether any challenge, appeal or further process is expected. They should also distinguish the publisher’s interpretation from findings or statements made by an authoritative body.

## Practical considerations

- Open the original {source_name} report and check every material name, date and quotation.
- Locate the primary decision, notice, filing or official statement where available.
- Confirm the jurisdiction, affected parties and current procedural position.
- Assess whether policies, contracts, reporting duties or compliance controls need review.
- Record what remains unconfirmed and avoid presenting allegations as established facts.
- Obtain tailored professional advice before acting on the media report.

## Questions the final article should answer

What exactly happened? Which facts are confirmed by primary material? Who is affected in {country_name}? Does the development create a new obligation or clarify an existing one? Is a response, appeal or further announcement expected? Answering these questions with verified sources will turn this draft into useful, original analysis rather than a summary of another publisher’s work.

## Source and verification note

This editable draft was generated from a selected Latest News result. It uses only details available in the search result and does not independently verify the publisher’s claims. Review, rewrite and supplement it with primary sources before submission.

Source: {source_name}
Original report: [Read the original report]({source_url})
"""

    excerpt = _truncate_words(
        f"{source_name} reports on {original_title}. This article reviews the "
        f"reported facts, context and practical implications for stakeholders in {country_name}.",
        300,
    )
    meta_description = _truncate_words(
        f"Read a fact-based analysis of {focus_keyword} in {country_name}, "
        f"including what {source_name} reported, the wider context and practical implications.",
        158,
    )
    tags = [
        country_name,
        industry,
        focus_keyword,
        "news analysis",
        source_name,
    ]
    tags = [re.sub(r"\s+", " ", tag).strip() for tag in tags if tag]

    initial = {
        "title": title,
        "slug": slugify(focus_keyword or title)[:70],
        "excerpt": excerpt,
        "body": body.strip(),
        "meta_title": _seo_title(title, country_name),
        "meta_description": meta_description,
        "focus_keyword": focus_keyword,
        "tags": ", ".join(dict.fromkeys(tags)),
        "status": "draft",
    }
    source = {
        "title": original_title,
        "url": source_url,
        "source_name": source_name,
        "published_at": published_at,
        "facts": facts,
        "facts_count": len(facts),
    }
    return initial, source
