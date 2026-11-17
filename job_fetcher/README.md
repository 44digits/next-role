# Job Fetcher

The fetcher is a separate, one-shot Python container. It reads a JSON
configuration from standard input, fetches listings through registered site
adapters, filters them, and submits matches to the authenticated Next Role
job-import API. It does not connect to the tracker database or run its own
scheduler.

## Configuration

Each company entry requires its name, one or more company links, keywords, and
one or more sites. Keywords use case-insensitive substring matching against a
posting's title and description. Set `keyword_match` to `any` or `all` per
company. `locations` is optional; when configured, known non-matching locations
are skipped, while an unknown posting location is included and logged.

Each site specifies an adapter identifier and URL. Optional `search_inputs`
are passed to that adapter for site-specific fields such as country or location.
`max_pages` defaults to 100 and bounds pagination. Site adapters are Python
modules in the project-level `adapters/` directory; each module must define a
`register(registry)` function. The directory is Git-ignored, so adapter code is
local to the working tree and must be present in the Docker build context.

Example configuration (replace the adapter identifier after an adapter has
been implemented):

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
          "adapter": "replace-with-implemented-adapter",
          "url": "https://careers.acme.example/jobs",
          "search_inputs": { "country": "CA" },
          "max_pages": 50
        }
      ]
    }
  ]
}
```

## Local invocation

Install the independently managed project dependencies and run its tests:

```sh
cd job_fetcher
uv sync
PYTHONPATH=src uv run python -m unittest discover -s tests
uv run ruff check src tests
uv run ruff format --check src tests
```

Start the tracker services, create a scraper service user's API token as
described in the root README, export the token, and pipe your JSON configuration
file through standard input:

```sh
cd ..
docker compose up --build -d
export JOB_IMPORT_API_TOKEN='replace-with-service-token'
docker compose --profile job-fetcher build job_fetcher
docker compose --profile job-fetcher run --rm -T --no-deps job_fetcher \
  < /path/to/job-fetcher-config.json
```

Use the same command from host cron for local scheduling. The JSON file stays on
the host and is piped to the container; it is not mounted. The API token is
provided separately through the environment and should be stored in a deployment
secret in cloud environments.

For a future Lambda deployment, `job_fetcher.lambda_handler.handler(event,
context)` accepts the event as the same JSON configuration object. A scheduled
event should pass that object as its input. API credentials remain environment
secrets.

## Adapters, errors, and logs

Implement `SiteAdapter.fetch_page(site, cursor)` in a Python module under
`adapters/`, then register it with the module's `register(registry)` function.
Prefer a site's documented public API/feed; otherwise implement site-specific
HTML retrieval and parsing. Adapters should raise `SiteScrapeError` for request
or parsing failures. Do not bypass login, anti-bot controls, site terms, robots
guidance, or rate limits.

See [example.md](./example.md) for a generic JSON-feed adapter, its registration,
and matching configuration and response examples.

The fetcher writes structured JSON logs to stdout. A site or posting failure is
recorded with company/site context and does not stop later companies from
running. The final summary reports imports, duplicates, skips, and failures;
the process exits nonzero after the run if any site or posting failed. Transient
job-import API errors are retried with bounded backoff.
