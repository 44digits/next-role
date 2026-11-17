from typing import Protocol

from .config import SiteConfig
from .models import PostingPage


class SiteScrapeError(Exception):
    """A site-specific request or parsing failure that can be isolated."""

    def __init__(self, message: str, *, phase: str = "fetch") -> None:
        super().__init__(message)
        self.phase = phase


class UnknownAdapterError(SiteScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, phase="adapter_resolution")


class PaginationError(SiteScrapeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, phase="pagination")


class SiteAdapter(Protocol):
    def fetch_page(self, site: SiteConfig, cursor: str | None) -> PostingPage:
        """Return one page and its next cursor, if any."""


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SiteAdapter] = {}

    def register(self, name: str, adapter: SiteAdapter) -> None:
        if not name.strip():
            raise ValueError("Adapter name must not be empty.")
        if name in self._adapters:
            raise ValueError(f"Adapter {name!r} is already registered.")
        self._adapters[name] = adapter

    def resolve(self, name: str) -> SiteAdapter:
        try:
            return self._adapters[name]
        except KeyError as error:
            raise UnknownAdapterError(
                f"No adapter is registered for {name!r}."
            ) from error
