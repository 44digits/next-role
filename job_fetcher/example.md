# Example JSON-feed adapter

This example shows a generic adapter for a site that exposes a documented JSON
jobs feed. It is not registered in the fetcher by default, and it is not wired
to a real job site. A real site may use different query parameters, response
fields, or pagination and would need its own adapter.

The adapter passes `search_inputs` as query parameters and sends the previous
page's cursor as a `cursor` query parameter. It expects the feed to return a
`jobs` array and an optional `next_cursor`.

## Adapter

Save this as `adapters/json_feed.py`:

```python
import json
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from job_fetcher.adapters import AdapterRegistry, SiteScrapeError
from job_fetcher.config import SiteConfig
from job_fetcher.models import JobPosting, PostingPage


class JsonFeedAdapter:
    def fetch_page(self, site: SiteConfig, cursor: str | None) -> PostingPage:
        parts = urlsplit(site.url)
        query = parse_qsl(parts.query, keep_blank_values=True)

        for key, value in site.search_inputs.items():
            if not isinstance(value, (str, int, float, bool)):
                raise SiteScrapeError(
                    f"Search input {key!r} must be a scalar value.",
                    phase="request",
                )
            query.append((key, str(value)))

        if cursor is not None:
            query.append(("cursor", cursor))

        request_url = urlunsplit(parts._replace(query=urlencode(query)))
        request = Request(request_url, headers={"Accept": "application/json"})

        try:
            with urlopen(request, timeout=15) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            raise SiteScrapeError(
                f"Could not fetch or parse the job feed: {error}",
                phase="fetch",
            ) from error

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise SiteScrapeError(
                "Job feed must contain a 'jobs' array.",
                phase="parse",
            )

        postings = []
        for record in payload["jobs"]:
            if not isinstance(record, dict):
                raise SiteScrapeError(
                    "Job feed contains an invalid job record.",
                    phase="parse",
                )

            title = record.get("title")
            url = record.get("url")
            description = record.get("description", "")
            location = record.get("location")

            if (
                not isinstance(title, str)
                or not title.strip()
                or not isinstance(url, str)
                or not url.strip()
                or not isinstance(description, str)
                or (location is not None and not isinstance(location, str))
            ):
                raise SiteScrapeError(
                    "Job record has invalid title, URL, description, or location.",
                    phase="parse",
                )

            postings.append(
                JobPosting(
                    title=title.strip(),
                    url=url.strip(),
                    description=description,
                    location=location,
                )
            )

        next_cursor = payload.get("next_cursor")
        if next_cursor is not None and (
            not isinstance(next_cursor, str) or not next_cursor
        ):
            raise SiteScrapeError(
                "Job feed returned an invalid cursor.",
                phase="parse",
            )

        return PostingPage(tuple(postings), next_cursor=next_cursor)


def register(registry: AdapterRegistry) -> None:
    registry.register("json_feed", JsonFeedAdapter())
```

`search_inputs` values in this example must be strings, numbers, or booleans.
The adapter translates request and parsing failures into `SiteScrapeError`, so
the runner can log the site failure and continue to other sites.

## Example configuration

The fetcher loads Python modules in `adapters/` and invokes each module's
`register` function. The `adapter` value must match the name passed to
`registry.register`:

```json
{
  "companies": [
    {
      "name": "Acme",
      "links": [
        { "label": "Website", "url": "https://acme.example" }
      ],
      "keywords": ["Python", "Django"],
      "keyword_match": "any",
      "locations": ["Remote", "Toronto"],
      "sites": [
        {
          "adapter": "json_feed",
          "url": "https://careers.acme.example/api/jobs",
          "search_inputs": {
            "country": "CA",
            "location": "Toronto"
          },
          "max_pages": 20
        }
      ]
    }
  ]
}
```

The adapter expects a response shaped like this:

```json
{
  "jobs": [
    {
      "title": "Python Engineer",
      "url": "https://careers.acme.example/jobs/42",
      "description": "Build services with Python and Django.",
      "location": "Remote"
    }
  ],
  "next_cursor": "page-2"
}
```

The final page should return `"next_cursor": null`. The runner handles keyword
and location filtering and submits matching postings to the job-import API.
Use documented feeds or APIs and follow the site's terms, robots guidance, and
rate limits.
