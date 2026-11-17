import logging
from uuid import uuid4

from .adapters import AdapterRegistry, PaginationError, SiteScrapeError
from .api_client import APIClientError
from .config import CompanyConfig, FetcherConfig, SiteConfig
from .filtering import match_posting
from .logging_utils import log_event
from .models import JobPosting, PostingPage, RunSummary


class JobFetcher:
    def __init__(
        self,
        config: FetcherConfig,
        adapters: AdapterRegistry,
        api_client,
        logger: logging.Logger,
        *,
        run_id: str | None = None,
    ) -> None:
        self.config = config
        self.adapters = adapters
        self.api_client = api_client
        self.logger = logger
        self.run_id = run_id or str(uuid4())

    def run(self) -> RunSummary:
        summary = RunSummary(companies=len(self.config.companies))
        log_event(
            self.logger,
            logging.INFO,
            "run_started",
            run_id=self.run_id,
            companies=summary.companies,
        )

        for company in self.config.companies:
            for site in company.sites:
                summary.sites += 1
                try:
                    self._process_site(company, site, summary)
                except SiteScrapeError as error:
                    summary.failures += 1
                    log_event(
                        self.logger,
                        logging.ERROR,
                        "site_failed",
                        run_id=self.run_id,
                        company=company.name,
                        adapter=site.adapter,
                        site_url=site.url,
                        phase=error.phase,
                        error_type=type(error).__name__,
                        error=str(error),
                    )

        log_event(
            self.logger,
            logging.INFO if summary.exit_code == 0 else logging.ERROR,
            "run_finished",
            run_id=self.run_id,
            exit_code=summary.exit_code,
            **summary.as_dict(),
        )
        return summary

    def _process_site(
        self,
        company: CompanyConfig,
        site: SiteConfig,
        summary: RunSummary,
    ) -> None:
        adapter = self.adapters.resolve(site.adapter)
        cursor = None
        seen_cursors: set[str] = set()

        for page_number in range(1, site.max_pages + 1):
            page = adapter.fetch_page(site, cursor)
            if not isinstance(page, PostingPage):
                raise SiteScrapeError(
                    f"Adapter {site.adapter!r} returned an invalid page."
                )
            summary.pages += 1
            log_event(
                self.logger,
                logging.INFO,
                "page_fetched",
                run_id=self.run_id,
                company=company.name,
                adapter=site.adapter,
                site_url=site.url,
                page=page_number,
                phase="fetch",
                postings=len(page.postings),
            )
            for posting in page.postings:
                self._process_posting(company, site, posting, summary)

            next_cursor = page.next_cursor
            if next_cursor is None:
                return
            if not isinstance(next_cursor, str) or not next_cursor:
                raise PaginationError(
                    f"Adapter {site.adapter!r} returned an invalid next cursor."
                )
            if next_cursor in seen_cursors:
                raise PaginationError(
                    f"Adapter {site.adapter!r} repeated a pagination cursor."
                )
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        raise PaginationError(
            f"Adapter {site.adapter!r} exceeded its {site.max_pages}-page limit."
        )

    def _process_posting(
        self,
        company: CompanyConfig,
        site: SiteConfig,
        posting: JobPosting,
        summary: RunSummary,
    ) -> None:
        summary.postings_seen += 1
        result = match_posting(company, posting)
        context = {
            "run_id": self.run_id,
            "company": company.name,
            "adapter": site.adapter,
            "site_url": site.url,
            "posting_url": posting.url,
        }
        if result.location_unknown:
            summary.location_unknown += 1
            log_event(
                self.logger,
                logging.WARNING,
                "posting_location_unknown",
                phase="filtering",
                **context,
            )
        if not result.accepted:
            if result.reason == "keywords":
                summary.skipped_keywords += 1
            elif result.reason == "location":
                summary.skipped_location += 1
            log_event(
                self.logger,
                logging.INFO,
                "posting_skipped",
                phase="filtering",
                reason=result.reason,
                **context,
            )
            return

        try:
            import_result = self.api_client.submit(company, posting)
        except APIClientError as error:
            summary.failures += 1
            log_event(
                self.logger,
                logging.ERROR,
                "posting_import_failed",
                phase="job_import",
                error_type=type(error).__name__,
                error=str(error),
                **context,
            )
            return

        if import_result.created:
            summary.imported += 1
            event = "posting_imported"
        else:
            summary.duplicates += 1
            event = "posting_duplicate"
        log_event(
            self.logger,
            logging.INFO,
            event,
            phase="job_import",
            job_id=import_result.job_id,
            **context,
        )
