import logging
import unittest

from job_fetcher.adapters import AdapterRegistry, SiteScrapeError
from job_fetcher.api_client import APIClientError
from job_fetcher.config import parse_config
from job_fetcher.models import ImportResult, JobPosting, PostingPage
from job_fetcher.runner import JobFetcher


def site_config(companies):
    return parse_config({"companies": companies})


def company(name, adapter, *, url=None, keywords=None):
    return {
        "name": name,
        "links": [{"label": "Website", "url": f"https://{name.lower()}.example"}],
        "keywords": keywords or ["python"],
        "sites": [
            {
                "adapter": adapter,
                "url": url or f"https://{name.lower()}.example/jobs",
                "max_pages": 5,
            }
        ],
    }


class FakeAdapter:
    def __init__(self, pages):
        self.pages = pages
        self.cursors = []

    def fetch_page(self, site, cursor):
        self.cursors.append(cursor)
        if isinstance(self.pages, Exception):
            raise self.pages
        index = 0 if cursor is None else int(cursor)
        return self.pages[index]


class FakeImporter:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.submissions = []

    def submit(self, company_config, posting):
        self.submissions.append((company_config.name, posting.url))
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return ImportResult(job_id=len(self.submissions), created=True, status="found")


def quiet_logger():
    logger = logging.Logger("test.job_fetcher")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


class RunnerTests(unittest.TestCase):
    def test_site_failure_is_logged_and_runner_continues_to_next_company(self):
        config = site_config(
            [
                company("Broken Co", "broken"),
                company("Working Co", "working"),
            ]
        )
        broken_adapter = FakeAdapter(SiteScrapeError("site timed out"))
        working_adapter = FakeAdapter(
            [
                PostingPage(
                    (
                        JobPosting(
                            title="Python developer",
                            url="https://working.example/jobs/1",
                        ),
                    )
                )
            ]
        )
        adapters = AdapterRegistry()
        adapters.register("broken", broken_adapter)
        adapters.register("working", working_adapter)
        importer = FakeImporter()

        summary = JobFetcher(
            config,
            adapters,
            importer,
            quiet_logger(),
            run_id="run-test",
        ).run()

        self.assertEqual(summary.failures, 1)
        self.assertEqual(summary.imported, 1)
        self.assertEqual(summary.exit_code, 1)
        self.assertEqual(
            importer.submissions, [("Working Co", "https://working.example/jobs/1")]
        )

    def test_pagination_fetches_pages_and_stops_at_terminal_page(self):
        config = site_config([company("Acme", "paged")])
        adapter = FakeAdapter(
            [
                PostingPage(
                    (JobPosting("Python one", "https://jobs.example/1"),),
                    next_cursor="1",
                ),
                PostingPage((JobPosting("Python two", "https://jobs.example/2"),)),
            ]
        )
        adapters = AdapterRegistry()
        adapters.register("paged", adapter)

        summary = JobFetcher(config, adapters, FakeImporter(), quiet_logger()).run()

        self.assertEqual(adapter.cursors, [None, "1"])
        self.assertEqual(summary.pages, 2)
        self.assertEqual(summary.imported, 2)
        self.assertEqual(summary.failures, 0)

    def test_repeated_pagination_cursor_is_a_site_failure(self):
        config = site_config([company("Acme", "loop")])
        adapter = FakeAdapter(
            [
                PostingPage((), next_cursor="1"),
                PostingPage((), next_cursor="1"),
            ]
        )
        adapters = AdapterRegistry()
        adapters.register("loop", adapter)

        summary = JobFetcher(config, adapters, FakeImporter(), quiet_logger()).run()

        self.assertEqual(summary.failures, 1)
        self.assertEqual(summary.exit_code, 1)

    def test_page_limit_failure_does_not_abort_later_company(self):
        config = site_config(
            [
                {
                    **company("Slow Co", "slow"),
                    "sites": [
                        {
                            "adapter": "slow",
                            "url": "https://slow.example/jobs",
                            "max_pages": 1,
                        }
                    ],
                },
                company("Fast Co", "fast"),
            ]
        )
        slow = FakeAdapter([PostingPage((), next_cursor="1")])
        fast = FakeAdapter(
            [PostingPage((JobPosting("Python engineer", "https://fast.example/1"),))]
        )
        adapters = AdapterRegistry()
        adapters.register("slow", slow)
        adapters.register("fast", fast)
        importer = FakeImporter()

        summary = JobFetcher(config, adapters, importer, quiet_logger()).run()

        self.assertEqual(summary.failures, 1)
        self.assertEqual(summary.imported, 1)
        self.assertEqual(importer.submissions[0][0], "Fast Co")

    def test_import_error_is_counted_and_later_postings_continue(self):
        config = site_config([company("Acme", "test")])
        adapter = FakeAdapter(
            [
                PostingPage(
                    (
                        JobPosting("Python one", "https://jobs.example/1"),
                        JobPosting("Python two", "https://jobs.example/2"),
                    )
                )
            ]
        )
        adapters = AdapterRegistry()
        adapters.register("test", adapter)
        importer = FakeImporter(
            [
                APIClientError("service unavailable"),
                ImportResult(job_id=2, created=True, status="found"),
            ]
        )

        summary = JobFetcher(config, adapters, importer, quiet_logger()).run()

        self.assertEqual(summary.failures, 1)
        self.assertEqual(summary.imported, 1)
        self.assertEqual(len(importer.submissions), 2)

    def test_keyword_misses_are_skipped_without_api_calls(self):
        config = site_config([company("Acme", "test", keywords=["golang"])])
        adapter = FakeAdapter(
            [PostingPage((JobPosting("Python engineer", "https://jobs.example/1"),))]
        )
        adapters = AdapterRegistry()
        adapters.register("test", adapter)
        importer = FakeImporter()

        summary = JobFetcher(config, adapters, importer, quiet_logger()).run()

        self.assertEqual(summary.skipped_keywords, 1)
        self.assertEqual(importer.submissions, [])


if __name__ == "__main__":
    unittest.main()
