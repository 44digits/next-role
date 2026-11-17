from dataclasses import dataclass

from .config import CompanyConfig
from .models import JobPosting


@dataclass(frozen=True)
class FilterResult:
    accepted: bool
    reason: str | None = None
    location_unknown: bool = False


def match_posting(company: CompanyConfig, posting: JobPosting) -> FilterResult:
    searchable_text = f"{posting.title}\n{posting.description}".casefold()
    matched_keywords = [
        keyword for keyword in company.keywords if keyword.casefold() in searchable_text
    ]

    if company.keyword_match == "all":
        matched = len(matched_keywords) == len(company.keywords)
    else:
        matched = bool(matched_keywords)
    if not matched:
        return FilterResult(accepted=False, reason="keywords")

    if not company.locations:
        return FilterResult(accepted=True)
    if not posting.location or not posting.location.strip():
        return FilterResult(accepted=True, location_unknown=True)
    location = posting.location.casefold()
    if not any(term.casefold() in location for term in company.locations):
        return FilterResult(accepted=False, reason="location")
    return FilterResult(accepted=True)
