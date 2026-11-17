import unittest

from job_fetcher.config import parse_config
from job_fetcher.filtering import match_posting
from job_fetcher.models import JobPosting


def make_company(*, keyword_match="any"):
    return parse_config(
        {
            "companies": [
                {
                    "name": "Acme",
                    "links": [{"label": "Website", "url": "https://acme.example"}],
                    "keywords": ["python", "django"],
                    "keyword_match": keyword_match,
                    "locations": ["Remote"],
                    "sites": [{"adapter": "test", "url": "https://jobs.example"}],
                }
            ]
        }
    ).companies[0]


class FilteringTests(unittest.TestCase):
    def test_any_keyword_matches_case_insensitively(self):
        result = match_posting(
            make_company(),
            JobPosting(
                title="Senior PYTHON Engineer",
                url="https://jobs.example/1",
                location="Remote - US",
            ),
        )

        self.assertTrue(result.accepted)
        self.assertIsNone(result.reason)

    def test_all_keyword_mode_requires_every_keyword(self):
        company = make_company(keyword_match="all")
        posting = JobPosting(
            title="Python Engineer",
            description="Build backend services",
            url="https://jobs.example/1",
            location="Remote",
        )

        result = match_posting(company, posting)

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "keywords")

    def test_known_location_mismatch_is_skipped(self):
        result = match_posting(
            make_company(),
            JobPosting(
                title="Python Engineer",
                url="https://jobs.example/1",
                location="New York",
            ),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "location")

    def test_unknown_location_is_included_and_reported(self):
        result = match_posting(
            make_company(),
            JobPosting(
                title="Python Engineer",
                url="https://jobs.example/1",
            ),
        )

        self.assertTrue(result.accepted)
        self.assertTrue(result.location_unknown)


if __name__ == "__main__":
    unittest.main()
