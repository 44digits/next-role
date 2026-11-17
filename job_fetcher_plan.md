# Scheduled job-site scraper

## Problem and approach

Build a separate, one-shot Python scraper application in its own container. At each externally scheduled run, it reads JSON configuration from standard input, retrieves postings with site-specific adapters, follows pagination, filters postings using configured keyword and optional location/country criteria, and submits matches to the existing authenticated Django job-import API. The scraper must not connect directly to the tracker database.

Keep the scraper independent of its scheduler and cloud provider: run it locally from cron and allow a future cloud scheduler or Lambda event to invoke the same container entry point. Keep site-specific behavior behind adapters so configuration can enable, disable, or reorder sites without changing the runner.

## Proposed scope and behavior

- **Container and scheduling**
  - Implement the scraper as a Python subproject with independently managed dependencies, aligned with the repository's Python version and `uv` workflow.
  - Package the scraper separately from the Django web container.
  - Make each invocation perform one complete run and exit with an appropriate success/failure status.
  - Delegate scheduling to the host or cloud platform; do not run a scheduler daemon inside the scraper container.
- **Configuration**
  - Require a validated JSON configuration at the start of each run, describing companies, job sites, adapter type, site URL, keywords, keyword match mode, and optional site-specific search inputs such as country or location.
  - Receive JSON on standard input for local container runs; a future cloud invocation adapter should pass its event payload to the same runner. Do not bake the changing company/site list into the image or require a mounted config file.
  - Allow a site to omit search inputs it does not support. Adapters should use supported remote filters where available and apply local filters to retrieved posting data as needed.
  - Make keyword matching configurable per company as any-keyword or all-keywords matching. Match keywords case-insensitively against available posting text.
- **Site adapters and pagination**
  - Define a common adapter interface for discovering, parsing, and paginating job postings while allowing site-specific request parameters and parsing logic.
  - Prefer documented public feeds or APIs when available; use a site-specific HTML adapter when needed.
  - Follow pagination until the adapter reports no next page, with a configurable safety limit to prevent unbounded runs.
  - If a requested location cannot be determined from a posting, include it and record that the location was unknown.
- **Import and duplicate handling**
  - Send matching postings to `POST /api/v1/job-imports/` using the existing token-authenticated API; do not share database credentials or write directly to PostgreSQL.
  - Send company name and website links, job title, and one `Job posting` link containing the posting URL; include notes only where appropriate.
  - Let the API create or reuse the company and apply its existing exact-URL duplicate behavior. A duplicate posting URL is an existing job; a different URL is submitted as a new job.
- **Run behavior and operations**
  - Emit structured Python logs to stdout with run ID, company, site/adapter, processing phase, and error details; local cron can capture stdout/stderr and cloud container platforms can collect the container logs.
  - Isolate failures by company/site: record the failed company, site, phase, and exception, then continue with the next company. Include counts of successes, imports, duplicates, skipped postings, and failures in a final run summary.
  - After processing all companies, return a nonzero exit status if any company/site failed so the scheduler can flag the partial failure.
  - Retry transient network/API failures with bounded backoff. Do not log API tokens.
  - Respect site terms, robots guidance, and rate limits; do not implement login or anti-bot circumvention.

## Implementation plan

1. Define the startup JSON schema, validation, and common job-posting/adapter interfaces.
2. Implement the one-shot runner, keyword and location filtering, pagination handling, API client, and per-site error reporting.
3. Add adapter implementations for selected job sites once their target URLs and behaviors are provided.
4. Package the Python scraper as a separate container, document local cron invocation and cloud-scheduler/Lambda invocation, and configure API credentials through deployment secrets.
5. Add focused tests for configuration, keyword/location behavior, adapter pagination, API payload/authentication, retries, and failure isolation across companies; document setup, logging, and adding adapters.

## Notes and considerations

- No initial company job sites have been selected. This plan covers the pluggable framework; implementing working site-specific adapters requires the initial target list.
- Environment variables are an alternative for small configurations but have platform size and exposure limits. An external configuration store is another future option for larger or centrally managed configurations, at the cost of retrieval credentials and service integration. Keep API credentials separate from the JSON criteria and provide them through deployment secrets.
- The existing API requires company links and exactly one job link labeled `Job posting`. It creates new jobs in the Job found stage and uses exact posting-URL matches to return an existing job.
- The selected behavior includes postings with unknown location. A future configuration change could choose to exclude them if that becomes preferable.
- Use a maximum-pages safety limit that is configurable per site; choose its default when implementing the config schema.
- Partial failures are logged and summarized; the run continues through all configured companies and returns a nonzero exit status at the end if any company/site failed.
