import io
import json
import unittest
from urllib.error import HTTPError

from job_fetcher.api_client import APIClientError, JobImportClient
from job_fetcher.config import parse_config
from job_fetcher.models import JobPosting


def company_config():
    return parse_config(
        {
            "companies": [
                {
                    "name": "Acme",
                    "links": [{"label": "Website", "url": "https://acme.example"}],
                    "keywords": ["python"],
                    "sites": [{"adapter": "test", "url": "https://jobs.example"}],
                }
            ]
        }
    ).companies[0]


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


class APIClientTests(unittest.TestCase):
    def test_submits_authenticated_payload_and_parses_created_response(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse(
                201,
                {"id": 42, "created": True, "status": "found"},
            )

        client = JobImportClient(
            "https://tracker.example",
            "secret-token",
            opener=opener,
        )
        result = client.submit(
            company_config(),
            JobPosting(
                title="Python Engineer",
                url="https://jobs.example/42",
                description="Do not copy the full description into notes.",
            ),
        )

        request, timeout = requests[0]
        self.assertEqual(
            request.full_url, "https://tracker.example/api/v1/job-imports/"
        )
        self.assertEqual(request.get_header("Authorization"), "Token secret-token")
        self.assertEqual(timeout, 15)
        payload = json.loads(request.data)
        self.assertEqual(payload["company"]["name"], "Acme")
        self.assertEqual(
            payload["job"]["links"],
            [{"label": "Job posting", "url": "https://jobs.example/42"}],
        )
        self.assertEqual(payload["job"]["notes"], "")
        self.assertTrue(result.created)
        self.assertEqual(result.job_id, 42)

    def test_retries_server_errors_with_bounded_backoff(self):
        calls = []
        waits = []

        def opener(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise HTTPError(
                    request.full_url,
                    503,
                    "Unavailable",
                    {},
                    io.BytesIO(b"try again"),
                )
            return FakeResponse(
                200,
                {"id": 17, "created": False, "status": "found"},
            )

        client = JobImportClient(
            "https://tracker.example",
            "secret-token",
            max_attempts=2,
            backoff_seconds=0.25,
            sleeper=waits.append,
            opener=opener,
        )
        result = client.submit(
            company_config(),
            JobPosting("Python Engineer", "https://jobs.example/17"),
        )

        self.assertFalse(result.created)
        self.assertEqual(len(calls), 2)
        self.assertEqual(waits, [0.25])

    def test_does_not_retry_client_errors(self):
        calls = []

        def opener(request, timeout):
            calls.append(request)
            raise HTTPError(
                request.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(b"invalid token"),
            )

        client = JobImportClient(
            "https://tracker.example",
            "secret-token",
            opener=opener,
            sleeper=lambda delay: self.fail("Client errors must not be retried."),
        )

        with self.assertRaises(APIClientError) as error:
            client.submit(
                company_config(),
                JobPosting("Python Engineer", "https://jobs.example/17"),
            )

        self.assertEqual(error.exception.status_code, 401)
        self.assertEqual(len(calls), 1)

    def test_api_error_response_redacts_the_service_token(self):
        def opener(request, timeout):
            raise HTTPError(
                request.full_url,
                400,
                "Bad request",
                {},
                io.BytesIO(b'{"detail":"secret-token"}'),
            )

        client = JobImportClient(
            "https://tracker.example",
            "secret-token",
            opener=opener,
        )

        with self.assertRaises(APIClientError) as error:
            client.submit(
                company_config(),
                JobPosting("Python Engineer", "https://jobs.example/17"),
            )

        self.assertNotIn("secret-token", str(error.exception))


if __name__ == "__main__":
    unittest.main()
