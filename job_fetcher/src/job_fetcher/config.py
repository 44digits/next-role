import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Link:
    label: str
    url: str


@dataclass(frozen=True)
class SiteConfig:
    adapter: str
    url: str
    search_inputs: dict[str, Any]
    max_pages: int


@dataclass(frozen=True)
class CompanyConfig:
    name: str
    links: tuple[Link, ...]
    keywords: tuple[str, ...]
    keyword_match: str
    locations: tuple[str, ...]
    sites: tuple[SiteConfig, ...]


@dataclass(frozen=True)
class FetcherConfig:
    companies: tuple[CompanyConfig, ...]


def load_config_json(raw: str) -> FetcherConfig:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}"
        ) from error
    return parse_config(payload)


def parse_config(payload: Any) -> FetcherConfig:
    root = _mapping(payload, "config")
    _check_keys(root, {"companies"}, {"companies"}, "config")
    companies_value = root["companies"]
    if not isinstance(companies_value, list) or not companies_value:
        raise ConfigurationError("config.companies must be a non-empty array.")

    companies = tuple(
        _parse_company(company, f"config.companies[{index}]")
        for index, company in enumerate(companies_value)
    )
    return FetcherConfig(companies=companies)


def _parse_company(value: Any, path: str) -> CompanyConfig:
    company = _mapping(value, path)
    _check_keys(
        company,
        {"name", "links", "keywords", "keyword_match", "locations", "sites"},
        {"name", "links", "keywords", "sites"},
        path,
    )

    links_value = company["links"]
    if not isinstance(links_value, list) or not links_value:
        raise ConfigurationError(f"{path}.links must be a non-empty array.")
    links = tuple(
        _parse_link(link, f"{path}.links[{index}]")
        for index, link in enumerate(links_value)
    )

    keywords = _string_array(company["keywords"], f"{path}.keywords", non_empty=True)
    keyword_match = company.get("keyword_match", "any")
    if not isinstance(keyword_match, str) or keyword_match not in {"any", "all"}:
        raise ConfigurationError(f"{path}.keyword_match must be 'any' or 'all'.")

    locations = _string_array(
        company.get("locations", []), f"{path}.locations", non_empty=False
    )
    sites_value = company["sites"]
    if not isinstance(sites_value, list) or not sites_value:
        raise ConfigurationError(f"{path}.sites must be a non-empty array.")
    sites = tuple(
        _parse_site(site, f"{path}.sites[{index}]")
        for index, site in enumerate(sites_value)
    )

    return CompanyConfig(
        name=_non_empty_string(company["name"], f"{path}.name"),
        links=links,
        keywords=keywords,
        keyword_match=keyword_match,
        locations=locations,
        sites=sites,
    )


def _parse_site(value: Any, path: str) -> SiteConfig:
    site = _mapping(value, path)
    _check_keys(
        site,
        {"adapter", "url", "search_inputs", "max_pages"},
        {"adapter", "url"},
        path,
    )

    search_inputs = site.get("search_inputs", {})
    if not isinstance(search_inputs, dict) or not all(
        isinstance(key, str) for key in search_inputs
    ):
        raise ConfigurationError(f"{path}.search_inputs must be a JSON object.")

    max_pages = site.get("max_pages", 100)
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ConfigurationError(f"{path}.max_pages must be a positive integer.")

    return SiteConfig(
        adapter=_non_empty_string(site["adapter"], f"{path}.adapter"),
        url=_http_url(site["url"], f"{path}.url"),
        search_inputs=search_inputs,
        max_pages=max_pages,
    )


def _parse_link(value: Any, path: str) -> Link:
    link = _mapping(value, path)
    _check_keys(link, {"label", "url"}, {"label", "url"}, path)
    return Link(
        label=_non_empty_string(link["label"], f"{path}.label"),
        url=_http_url(link["url"], f"{path}.url"),
    )


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{path} must be a JSON object.")
    return value


def _check_keys(
    value: dict[str, Any],
    allowed: set[str],
    required: set[str],
    path: str,
) -> None:
    missing = required - value.keys()
    extra = value.keys() - allowed
    if missing:
        names = ", ".join(sorted(missing))
        raise ConfigurationError(f"{path} is missing required field(s): {names}.")
    if extra:
        names = ", ".join(sorted(extra))
        raise ConfigurationError(f"{path} has unknown field(s): {names}.")


def _non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{path} must be a non-empty string.")
    return value.strip()


def _string_array(value: Any, path: str, *, non_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{path} must be an array of strings.")
    items = tuple(
        _non_empty_string(item, f"{path}[{index}]") for index, item in enumerate(value)
    )
    if non_empty and not items:
        raise ConfigurationError(f"{path} must contain at least one string.")
    return items


def _http_url(value: Any, path: str) -> str:
    url = _non_empty_string(value, path)
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise ConfigurationError(
            f"{path} must be an absolute HTTP or HTTPS URL."
        ) from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError(f"{path} must be an absolute HTTP or HTTPS URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError(f"{path} must not contain embedded credentials.")
    return url
