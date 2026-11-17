import json
import time
from collections.abc import Mapping
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from .config import CompanyConfig, ConfigurationError
from .models import ImportResult, JobPosting


class APIClientError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JobImportClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 15,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 4,
        opener: Callable = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        try:
            parsed_url = urlsplit(base_url)
        except ValueError as error:
            raise ConfigurationError(
                "JOB_IMPORT_API_URL must be an absolute HTTP or HTTPS URL."
            ) from error
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ConfigurationError(
                "JOB_IMPORT_API_URL must be an absolute HTTP or HTTPS URL."
            )
        if parsed_url.username is not None or parsed_url.password is not None:
            raise ConfigurationError(
                "JOB_IMPORT_API_URL must not contain embedded credentials."
            )
        if not token.strip():
            raise ConfigurationError("JOB_IMPORT_API_TOKEN must not be empty.")
        if timeout <= 0 or max_attempts < 1:
            raise ValueError("Timeout and max_attempts must be positive.")
        if backoff_seconds < 0 or max_backoff_seconds < 0:
            raise ValueError("Backoff delays must not be negative.")
        self.endpoint = urljoin(base_url.rstrip("/") + "/", "api/v1/job-imports/")
        self.token = token
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self._opener = opener
        self._sleep = sleeper

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "JobImportClient":
        base_url = environment.get("JOB_IMPORT_API_URL", "")
        token = environment.get("JOB_IMPORT_API_TOKEN", "")
        if not base_url:
            raise ConfigurationError("JOB_IMPORT_API_URL must be configured.")
        if not token:
            raise ConfigurationError("JOB_IMPORT_API_TOKEN must be configured.")
        return cls(base_url, token)

    def submit(self, company: CompanyConfig, posting: JobPosting) -> ImportResult:
        payload = {
            "company": {
                "name": company.name,
                "links": [
                    {"label": link.label, "url": link.url} for link in company.links
                ],
            },
            "job": {
                "title": posting.title,
                "links": [{"label": "Job posting", "url": posting.url}],
                "notes": "",
            },
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        status_code, body = self._send(request)
        try:
            response_data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise APIClientError(
                "Job import API returned invalid JSON.", status_code=status_code
            ) from error
        if not isinstance(response_data, dict):
            raise APIClientError(
                "Job import API response must be a JSON object.",
                status_code=status_code,
            )
        job_id = response_data.get("id")
        created = response_data.get("created")
        result_status = response_data.get("status")
        if (
            isinstance(job_id, bool)
            or not isinstance(job_id, int)
            or not isinstance(created, bool)
            or not isinstance(result_status, str)
        ):
            raise APIClientError(
                "Job import API response is missing required fields.",
                status_code=status_code,
            )
        if (status_code == 201) != created:
            raise APIClientError(
                "Job import API response status conflicts with its created flag.",
                status_code=status_code,
            )
        return ImportResult(job_id=job_id, created=created, status=result_status)

    def _send(self, request: Request) -> tuple[int, bytes]:
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    status_code = response.status
                    body = response.read()
            except HTTPError as error:
                status_code = error.code
                body = error.read()
            except (TimeoutError, URLError, OSError) as error:
                if attempt < self.max_attempts:
                    self._wait(attempt)
                    continue
                raise APIClientError(
                    f"Job import API request failed: {error}"
                ) from error

            if status_code in {429, *range(500, 600)}:
                if attempt < self.max_attempts:
                    self._wait(attempt)
                    continue
                raise APIClientError(
                    f"Job import API returned HTTP {status_code}.",
                    status_code=status_code,
                )
            if status_code not in {200, 201}:
                detail = body.decode("utf-8", errors="replace")[:500].replace(
                    self.token, "[redacted]"
                )
                raise APIClientError(
                    f"Job import API returned HTTP {status_code}: {detail}",
                    status_code=status_code,
                )
            return status_code, body

        raise AssertionError("Retry loop exited unexpectedly.")

    def _wait(self, attempt: int) -> None:
        delay = min(
            self.backoff_seconds * (2 ** (attempt - 1)),
            self.max_backoff_seconds,
        )
        self._sleep(delay)
